/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Copyright (C) 2022, Tomi Valkeinen <tomi.valkeinen@ideasonboard.com>
 */

#include "py_camera_manager.h"

#include <algorithm>
#include <errno.h>
#include <memory>
#include <sys/eventfd.h>
#include <system_error>
#include <unistd.h>
#include <vector>

#include "py_main.h"

namespace py = pybind11;

using namespace libcamera;

PyCameraManager::PyCameraManager()
{
	LOG(Python, Debug) << "PyCameraManager()";

	cameraManager_ = std::make_unique<CameraManager>();

	int fd = eventfd(0, EFD_CLOEXEC | EFD_NONBLOCK);
	if (fd == -1)
		throw std::system_error(errno, std::generic_category(),
					"Failed to create eventfd");

	eventFd_ = UniqueFD(fd);

	int ret = cameraManager_->start();
	if (ret)
		throw std::system_error(-ret, std::generic_category(),
					"Failed to start CameraManager");

	cameraManager_->cameraAdded.connect(this, &PyCameraManager::handleCameraAdded);
	cameraManager_->cameraRemoved.connect(this, &PyCameraManager::handleCameraRemoved);
}

PyCameraManager::~PyCameraManager()
{
	LOG(Python, Debug) << "~PyCameraManager()";

	cameraManager_->cameraAdded.disconnect();
	cameraManager_->cameraRemoved.disconnect();
}

py::list PyCameraManager::cameras()
{
	/*
	 * Create a list of Cameras, where each camera has a keep-alive to
	 * CameraManager.
	 */
	py::list l;

	for (auto &camera : cameraManager_->cameras()) {
		py::object py_cm = py::cast(this);
		py::object py_cam = py::cast(camera);
		py::detail::keep_alive_impl(py_cam, py_cm);
		l.append(py_cam);
	}

	return l;
}

PyCameraEvent PyCameraManager::convertEvent(const CameraEvent &event)
{
	/*
	 * We need to set a keep-alive here so that the camera keeps the
	 * camera manager alive.
	 */
	py::object py_cm = py::cast(this);
	py::object py_cam = py::cast(event.camera_);
	py::detail::keep_alive_impl(py_cam, py_cm);

	PyCameraEvent pyevent(event.type_, py_cam);

	switch (event.type_) {
	case CameraEventType::CameraAdded:
	case CameraEventType::CameraRemoved:
	case CameraEventType::Disconnect:
		/* No additional parameters to add */
		break;

	case CameraEventType::BufferCompleted:
		pyevent.request_ = py::cast(event.request_);
		pyevent.fb_ = py::cast(event.fb_);
		break;

	case CameraEventType::RequestCompleted:
		pyevent.request_ = py::cast(event.request_);

		/* Decrease the ref increased in Camera.queue_request() */
		pyevent.request_.dec_ref();

		break;
	}

	return pyevent;
}

std::vector<PyCameraEvent> PyCameraManager::getPyEvents()
{
	int ret = readFd();

	if (ret == EAGAIN) {
		LOG(Python, Debug) << "No events";
		return {};
	}

	if (ret != 0)
		throw std::system_error(ret, std::generic_category());

	std::vector<CameraEvent> events = getEvents();

	LOG(Python, Debug) << "Got " << events.size() << " events";

	std::vector<PyCameraEvent> pyevents;
	pyevents.reserve(events.size());

	std::transform(events.begin(), events.end(), std::back_inserter(pyevents),
		       [this](const CameraEvent &ev) {
			       return convertEvent(ev);
		       });

	return pyevents;
}

static bool isCameraSpecificEvent(const CameraEvent &event, std::shared_ptr<Camera> &camera)
{
	return event.camera_ == camera &&
	       (event.type_ == CameraEventType::RequestCompleted ||
		event.type_ == CameraEventType::BufferCompleted ||
		event.type_ == CameraEventType::Disconnect);
}

std::vector<PyCameraEvent> PyCameraManager::getPyCameraEvents(std::shared_ptr<Camera> camera)
{
	std::vector<CameraEvent> events;
	size_t unhandled_size;

	{
		MutexLocker guard(eventsMutex_);

		/*
		 * Collect events related to the given camera and remove them
		 * from the events_ vector.
		 */

		auto it = events_.begin();
		while (it != events_.end()) {
			if (isCameraSpecificEvent(*it, camera)) {
				events.push_back(*it);
				it = events_.erase(it);
			} else {
				it++;
			}
		}

		unhandled_size = events_.size();
	}

	/* Convert events to Python events */

	std::vector<PyCameraEvent> pyevents;

	for (const auto &event : events) {
		PyCameraEvent pyev = convertEvent(event);
		pyevents.push_back(pyev);
	}

	LOG(Python, Debug) << "Got " << pyevents.size() << " camera events, "
			   << unhandled_size << " unhandled events left";

	return pyevents;
}

/* Note: Called from another thread */
void PyCameraManager::handleBufferCompleted(std::shared_ptr<Camera> cam, Request *req, FrameBuffer *fb)
{
	CameraEvent ev(CameraEventType::BufferCompleted, cam, req, fb);

	pushEvent(ev);
}

/* Note: Called from another thread */
void PyCameraManager::handleRequestCompleted(std::shared_ptr<Camera> cam, Request *req)
{
	CameraEvent ev(CameraEventType::RequestCompleted, cam, req);

	pushEvent(ev);
}

/* Note: Called from another thread */
void PyCameraManager::handleDisconnected(std::shared_ptr<Camera> cam)
{
	CameraEvent ev(CameraEventType::Disconnect, cam);

	pushEvent(ev);
}

/* Note: Called from another thread */
void PyCameraManager::handleCameraAdded(std::shared_ptr<Camera> cam)
{
	CameraEvent ev(CameraEventType::CameraAdded, cam);

	pushEvent(ev);
}

/* Note: Called from another thread */
void PyCameraManager::handleCameraRemoved(std::shared_ptr<Camera> cam)
{
	CameraEvent ev(CameraEventType::CameraRemoved, cam);

	pushEvent(ev);
}

void PyCameraManager::writeFd()
{
	uint64_t v = 1;

	size_t s = write(eventFd_.get(), &v, 8);
	/*
	 * We should never fail, and have no simple means to manage the error,
	 * so let's log a fatal error.
	 */
	if (s != 8)
		LOG(Python, Fatal) << "Unable to write to eventfd";
}

int PyCameraManager::readFd()
{
	uint8_t buf[8];

	ssize_t ret = read(eventFd_.get(), buf, 8);

	if (ret == 8)
		return 0;
	else if (ret < 0)
		return -errno;
	else
		return -EIO;
}

void PyCameraManager::pushEvent(const CameraEvent &ev)
{
	{
		MutexLocker guard(eventsMutex_);
		events_.push_back(ev);
	}

	writeFd();

	LOG(Python, Debug) << "Queued events: " << events_.size();
}

std::vector<CameraEvent> PyCameraManager::getEvents()
{
	std::vector<CameraEvent> v;

	MutexLocker guard(eventsMutex_);
	swap(v, events_);

	return v;
}
