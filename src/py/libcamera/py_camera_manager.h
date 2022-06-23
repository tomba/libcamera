/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Copyright (C) 2022, Tomi Valkeinen <tomi.valkeinen@ideasonboard.com>
 */

#pragma once

#include <mutex>

#include <libcamera/libcamera.h>

#include <pybind11/smart_holder.h>

using namespace libcamera;

class PyCameraManager : public CameraManager
{
public:
	PyCameraManager();
	virtual ~PyCameraManager();

	pybind11::list getCameras();

	int eventFd() const { return eventFd_; }

	std::vector<pybind11::object> getReadyRequests(bool nonBlocking = false);

	void handleRequestCompleted(Request *req);

private:
	int eventFd_ = -1;
	std::mutex completedRequestsMutex_;
	std::vector<Request *> completedRequests_;

	void writeFd();
	void readFd();
	void pushRequest(Request *req);
	std::vector<Request *> getCompletedRequests();
	bool hasEvents();
};
