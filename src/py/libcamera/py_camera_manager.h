/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Copyright (C) 2022, Tomi Valkeinen <tomi.valkeinen@ideasonboard.com>
 */

#pragma once

#include <mutex>

#include <libcamera/libcamera.h>

#include <pybind11/smart_holder.h>

using namespace libcamera;

struct CameraEvent;

class PyCameraManager : public CameraManager
{
public:
	PyCameraManager();
	virtual ~PyCameraManager();

	pybind11::list getCameras();

	int eventFd() const { return eventFd_; }

	std::vector<pybind11::object> getReadyRequests(bool nonBlocking = false);

	void handleRequestCompleted(Request *req);

	void handleBufferCompleted(std::shared_ptr<Camera> cam, Request *req, FrameBuffer *fb);
	void handleRequestCompleted(std::shared_ptr<Camera> cam, Request *req);
	void handleDisconnected(std::shared_ptr<Camera> cam);
	void handleCameraAdded(std::shared_ptr<Camera> cam);
	void handleCameraRemoved(std::shared_ptr<Camera> cam);

	void dispatchEvents(bool nonBlocking = false);
	void discardEvents();

	std::function<void(std::shared_ptr<Camera>)> getCameraAdded() const;
	void setCameraAdded(std::function<void(std::shared_ptr<Camera>)> fun);

	std::function<void(std::shared_ptr<Camera>)> getCameraRemoved() const;
	void setCameraRemoved(std::function<void(std::shared_ptr<Camera>)> fun);

	std::function<void(std::shared_ptr<Camera>, Request *)> getRequestCompleted(Camera *cam);
	void setRequestCompleted(Camera *cam, std::function<void(std::shared_ptr<Camera>, Request *)> fun);

	std::function<void(std::shared_ptr<Camera>, Request *, FrameBuffer *)> getBufferCompleted(Camera *cam);
	void setBufferCompleted(Camera *cam, std::function<void(std::shared_ptr<Camera>, Request *, FrameBuffer *)> fun);

	std::function<void(std::shared_ptr<Camera>)> getDisconnected(Camera *cam);
	void setDisconnected(Camera *cam, std::function<void(std::shared_ptr<Camera>)> fun);

private:
	int eventFd_ = -1;
	std::mutex cameraEventsMutex_;
	std::vector<CameraEvent> cameraEvents_;

	std::function<void(std::shared_ptr<Camera>)> cameraAddedHandler_;
	std::function<void(std::shared_ptr<Camera>)> cameraRemovedHandler_;

	std::map<Camera *, std::function<void(std::shared_ptr<Camera>, Request *, FrameBuffer *)>> cameraBufferCompletedHandlers_;
	std::map<Camera *, std::function<void(std::shared_ptr<Camera>, Request *)>> cameraRequestCompletedHandlers_;
	std::map<Camera *, std::function<void(std::shared_ptr<Camera>)>> cameraDisconnectHandlers_;

	void writeFd();
	void readFd();
	void pushEvent(const CameraEvent &ev);
	std::vector<CameraEvent> getEvents();
	bool hasEvents();
};
