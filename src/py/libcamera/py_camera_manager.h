/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Copyright (C) 2022, Tomi Valkeinen <tomi.valkeinen@ideasonboard.com>
 */

#pragma once

#include <libcamera/base/mutex.h>

#include <libcamera/libcamera.h>

#include <pybind11/smart_holder.h>

using namespace libcamera;

enum class CameraEventType {
	CameraAdded,
	CameraRemoved,
	Disconnect,
	RequestCompleted,
	BufferCompleted,
};

/*
 * This event struct is used internally to queue the events we receive from
 * other threads.
 */
struct CameraEvent {
	CameraEvent(CameraEventType type, std::shared_ptr<Camera> camera,
		    Request *request = nullptr, FrameBuffer *fb = nullptr)
		: type_(type), camera_(camera), request_(request), fb_(fb)
	{
	}

	CameraEventType type_;
	std::shared_ptr<Camera> camera_;
	Request *request_;
	FrameBuffer *fb_;
};

/*
 * This event struct is passed to Python. We need to use pybind11::object here
 * instead of a C++ pointer so that we keep a ref to the Request, and a
 * keep-alive from the camera to the camera manager.
 */
struct PyCameraEvent {
	PyCameraEvent(CameraEventType type, pybind11::object camera)
		: type_(type), camera_(camera)
	{
	}

	CameraEventType type_;
	pybind11::object camera_;
	pybind11::object request_;
	pybind11::object fb_;
};

class PyCameraManager
{
public:
	PyCameraManager();
	~PyCameraManager();

	pybind11::list cameras();
	std::shared_ptr<Camera> get(const std::string &name) { return cameraManager_->get(name); }

	static const std::string &version() { return CameraManager::version(); }

	int eventFd() const { return eventFd_.get(); }

	std::vector<PyCameraEvent> getPyEvents();
	std::vector<PyCameraEvent> getPyCameraEvents(std::shared_ptr<Camera> camera);

	void handleBufferCompleted(std::shared_ptr<Camera> cam, Request *req, FrameBuffer *fb);
	void handleRequestCompleted(std::shared_ptr<Camera> cam, Request *req);
	void handleDisconnected(std::shared_ptr<Camera> cam);
	void handleCameraAdded(std::shared_ptr<Camera> cam);
	void handleCameraRemoved(std::shared_ptr<Camera> cam);

	bool bufferCompletedEventActive_ = false;

private:
	std::unique_ptr<CameraManager> cameraManager_;

	UniqueFD eventFd_;
	libcamera::Mutex eventsMutex_;
	std::vector<CameraEvent> events_
		LIBCAMERA_TSA_GUARDED_BY(eventsMutex_);

	void writeFd();
	int readFd();
	void pushEvent(const CameraEvent &ev);
	std::vector<CameraEvent> getEvents();

	PyCameraEvent convertEvent(const CameraEvent &event);
};
