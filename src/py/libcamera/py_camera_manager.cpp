/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Copyright (C) 2022, Tomi Valkeinen <tomi.valkeinen@ideasonboard.com>
 */

#include "py_camera_manager.h"

#include <cerrno>
#include <poll.h>
#include <sys/eventfd.h>
#include <system_error>
#include <unistd.h>

#include "py_main.h"

namespace py = pybind11;

using namespace libcamera;

struct CameraEvent {
	enum class EventType {
		Undefined = 0,
		CameraAdded,
		CameraRemoved,
		Disconnect,
		RequestCompleted,
		BufferCompleted,
	};

	CameraEvent(EventType type)
		: type(type)
	{
	}

	EventType type;

	std::shared_ptr<Camera> cam;

	union {
		struct {
			Request *req;
			FrameBuffer *fb;
		} buf_completed;

		struct {
			Request *req;
		} req_completed;
	};
};

PyCameraManager::PyCameraManager()
{
	printf("PyCameraManager()\n");

	int fd = eventfd(0, 0);
	if (fd == -1)
		throw std::system_error(errno, std::generic_category(),
					"Failed to create eventfd");

	eventFd_ = fd;

	int ret = start();
	if (ret) {
		close(fd);
		eventFd_ = -1;
		throw std::system_error(-ret, std::generic_category(),
					"Failed to start CameraManager");
	}
}

PyCameraManager::~PyCameraManager()
{
	printf("~PyCameraManager()\n");

	if (eventFd_ != -1) {
		close(eventFd_);
		eventFd_ = -1;
	}
}

py::list PyCameraManager::getCameras()
{
	/*
	 * Create a list of Cameras, where each camera has a keep-alive to
	 * CameraManager.
	 */
	py::list l;

	for (auto &camera : cameras()) {
		py::object py_cm = py::cast(this);
		py::object py_cam = py::cast(camera);
		py::detail::keep_alive_impl(py_cam, py_cm);
		l.append(py_cam);
	}

	return l;
}

/* DEPRECATED */
std::vector<py::object> PyCameraManager::getReadyRequests(bool nonBlocking)
{
	if (!nonBlocking || hasEvents())
		readFd();

	std::vector<py::object> ret;

	for (const auto &ev : getEvents()) {
		switch (ev.type) {
		case CameraEvent::EventType::RequestCompleted: {
			Request *req = ev.req_completed.req;
			py::object o = py::cast(req);
			/* Decrease the ref increased in Camera.queue_request() */
			o.dec_ref();
			ret.push_back(o);
		}
		default:
			/* ignore */
			break;
		}
	}

	return ret;
}

/* Note: Called from another thread */
void PyCameraManager::handleBufferCompleted(std::shared_ptr<Camera> cam, Request *req, FrameBuffer *fb)
{
	CameraEvent ev(CameraEvent::EventType::BufferCompleted);
	ev.cam = cam;
	ev.buf_completed.req = req;
	ev.buf_completed.fb = fb;

	pushEvent(ev);
	writeFd();
}

/* Note: Called from another thread */
void PyCameraManager::handleRequestCompleted(std::shared_ptr<Camera> cam, Request *req)
{
	CameraEvent ev(CameraEvent::EventType::RequestCompleted);
	ev.cam = cam;
	ev.req_completed.req = req;

	pushEvent(ev);
	writeFd();
}

/* Note: Called from another thread */
void PyCameraManager::handleDisconnected(std::shared_ptr<Camera> cam)
{
	CameraEvent ev(CameraEvent::EventType::Disconnect);
	ev.cam = cam;

	pushEvent(ev);
	writeFd();
}

/* Note: Called from another thread */
void PyCameraManager::handleCameraAdded(std::shared_ptr<Camera> cam)
{
	CameraEvent ev(CameraEvent::EventType::CameraAdded);
	ev.cam = cam;

	pushEvent(ev);
	writeFd();
}

/* Note: Called from another thread */
void PyCameraManager::handleCameraRemoved(std::shared_ptr<Camera> cam)
{
	CameraEvent ev(CameraEvent::EventType::CameraRemoved);
	ev.cam = cam;

	pushEvent(ev);
	writeFd();
}

void PyCameraManager::dispatchEvents(bool nonBlocking)
{
	if (!nonBlocking || hasEvents())
		readFd();

	std::vector<CameraEvent> v = getEvents();

	LOG(Python, Debug) << "Dispatch " << v.size() << " events";

	for (const auto &ev : v) {
		switch (ev.type) {
		case CameraEvent::EventType::CameraAdded: {
			std::shared_ptr<Camera> cam = ev.cam;

			if (cameraAddedHandler_)
				cameraAddedHandler_(cam);

			break;
		}
		case CameraEvent::EventType::CameraRemoved: {
			std::shared_ptr<Camera> cam = ev.cam;

			if (cameraRemovedHandler_)
				cameraRemovedHandler_(cam);

			break;
		}
		case CameraEvent::EventType::BufferCompleted: {
			std::shared_ptr<Camera> cam = ev.cam;

			auto cb = getBufferCompleted(cam.get());

			if (cb)
				cb(cam, ev.buf_completed.req, ev.buf_completed.fb);

			break;
		}
		case CameraEvent::EventType::RequestCompleted: {
			std::shared_ptr<Camera> cam = ev.cam;

			auto cb = getRequestCompleted(cam.get());

			if (cb)
				cb(cam, ev.req_completed.req);

			/* Decrease the ref increased in Camera.queue_request() */
			py::object o = py::cast(ev.req_completed.req);
			o.dec_ref();

			break;
		}
		case CameraEvent::EventType::Disconnect: {
			std::shared_ptr<Camera> cam = ev.cam;

			auto cb = getDisconnected(cam.get());

			if (cb)
				cb(cam);

			break;
		}
		default:
			assert(false);
		}
	}
}

void PyCameraManager::discardEvents()
{
	if (hasEvents())
		readFd();

	std::vector<CameraEvent> v = getEvents();

	LOG(Python, Debug) << "Discard " << v.size() << " events";

	for (const auto &ev : v) {
		if (ev.type != CameraEvent::EventType::RequestCompleted)
			continue;

		std::shared_ptr<Camera> cam = ev.cam;

		/* Decrease the ref increased in Camera.queue_request() */
		py::object o = py::cast(ev.req_completed.req);
		o.dec_ref();
	}
}

std::function<void(std::shared_ptr<Camera>)> PyCameraManager::getCameraAdded() const
{
	return cameraAddedHandler_;
}

void PyCameraManager::setCameraAdded(std::function<void(std::shared_ptr<Camera>)> fun)
{
	if (cameraAddedHandler_)
		cameraAdded.disconnect();

	cameraAddedHandler_ = fun;

	if (fun)
		cameraAdded.connect(this, &PyCameraManager::handleCameraAdded);
}

std::function<void(std::shared_ptr<Camera>)> PyCameraManager::getCameraRemoved() const
{
	return cameraRemovedHandler_;
}

void PyCameraManager::setCameraRemoved(std::function<void(std::shared_ptr<Camera>)> fun)
{
	if (cameraRemovedHandler_)
		cameraRemoved.disconnect();

	cameraRemovedHandler_ = fun;

	if (fun)
		cameraRemoved.connect(this, &PyCameraManager::handleCameraRemoved);
}

std::function<void(std::shared_ptr<Camera>, Request *)> PyCameraManager::getRequestCompleted(Camera *cam)
{
	if (auto it = cameraRequestCompletedHandlers_.find(cam);
	    it != cameraRequestCompletedHandlers_.end())
		return it->second;

	return nullptr;
}

void PyCameraManager::setRequestCompleted(Camera *cam, std::function<void(std::shared_ptr<Camera>, Request *)> fun)
{
	if (fun)
		cameraRequestCompletedHandlers_[cam] = fun;
	else
		cameraRequestCompletedHandlers_.erase(cam);
}

std::function<void(std::shared_ptr<Camera>, Request *, FrameBuffer *)> PyCameraManager::getBufferCompleted(Camera *cam)
{
	if (auto it = cameraBufferCompletedHandlers_.find(cam);
	    it != cameraBufferCompletedHandlers_.end())
		return it->second;

	return nullptr;
}

void PyCameraManager::setBufferCompleted(Camera *cam, std::function<void(std::shared_ptr<Camera>, Request *, FrameBuffer *)> fun)
{
	if (fun)
		cameraBufferCompletedHandlers_[cam] = fun;
	else
		cameraBufferCompletedHandlers_.erase(cam);
}

std::function<void(std::shared_ptr<Camera>)> PyCameraManager::getDisconnected(Camera *cam)
{
	if (auto it = cameraDisconnectHandlers_.find(cam);
	    it != cameraDisconnectHandlers_.end())
		return it->second;

	return nullptr;
}

void PyCameraManager::setDisconnected(Camera *cam, std::function<void(std::shared_ptr<Camera>)> fun)
{
	if (fun)
		cameraDisconnectHandlers_[cam] = fun;
	else
		cameraDisconnectHandlers_.erase(cam);
}

void PyCameraManager::writeFd()
{
	uint64_t v = 1;

	size_t s = write(eventFd_, &v, 8);
	/*
	 * We should never fail, and have no simple means to manage the error,
	 * so let's log a fatal error.
	 */
	if (s != 8)
		LOG(Python, Fatal) << "Unable to write to eventfd";
}

void PyCameraManager::readFd()
{
	uint8_t buf[8];

	if (read(eventFd_, buf, 8) != 8)
		throw std::system_error(errno, std::generic_category());
}

void PyCameraManager::pushEvent(const CameraEvent &ev)
{
	std::lock_guard guard(cameraEventsMutex_);
	cameraEvents_.push_back(ev);

	LOG(Python, Debug) << "Queued events: " << cameraEvents_.size();
}

std::vector<CameraEvent> PyCameraManager::getEvents()
{
	std::vector<CameraEvent> v;
	std::lock_guard guard(cameraEventsMutex_);
	swap(v, cameraEvents_);
	return v;
}

bool PyCameraManager::hasEvents()
{
	struct pollfd pfd = {
		.fd = eventFd_,
		.events = POLLIN,
		.revents = 0,
	};

	int ret = poll(&pfd, 1, 0);
	if (ret == -1)
		throw std::system_error(errno, std::generic_category());

	return pfd.revents & POLLIN;
}
