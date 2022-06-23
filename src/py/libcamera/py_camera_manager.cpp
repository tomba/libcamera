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

std::vector<py::object> PyCameraManager::getReadyRequests(bool nonBlocking)
{
	if (!nonBlocking || hasEvents())
		readFd();

	std::vector<py::object> ret;

	for (Request *request : getCompletedRequests()) {
		py::object o = py::cast(request);
		/* Decrease the ref increased in Camera.queue_request() */
		o.dec_ref();
		ret.push_back(o);
	}

	return ret;
}

/* Note: Called from another thread */
void PyCameraManager::handleRequestCompleted(Request *req)
{
	pushRequest(req);
	writeFd();
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

void PyCameraManager::pushRequest(Request *req)
{
	std::lock_guard guard(completedRequestsMutex_);
	completedRequests_.push_back(req);
}

std::vector<Request *> PyCameraManager::getCompletedRequests()
{
	std::vector<Request *> v;
	std::lock_guard guard(completedRequestsMutex_);
	swap(v, completedRequests_);
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
