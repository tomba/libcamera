/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Copyright (C) 2020, Google Inc.
 *
 * vivid.cpp - Pipeline handler for the vivid capture device
 */

#include <libcamera/base/log.h>

#include "libcamera/internal/pipeline_handler.h"

/*
 * Explicitly disable the unused-parameter warning in this pipeline handler.
 *
 * Parameters are left unused while they are introduced incrementally, so for
 * documentation purposes only we disable this warning so that we can compile
 * each commit independently without breaking the flow of the development
 * additions.
 *
 * This is not recommended practice within libcamera, please listen to your
 * compiler warnings.
 */
#pragma GCC diagnostic ignored "-Wunused-parameter"

namespace libcamera {

LOG_DEFINE_CATEGORY(VIVID)

class PipelineHandlerVivid : public PipelineHandler
{
public:
	PipelineHandlerVivid(CameraManager *manager);

	CameraConfiguration *generateConfiguration(Camera *camera,
						   const StreamRoles &roles) override;
	int configure(Camera *camera, CameraConfiguration *config) override;

	int exportFrameBuffers(Camera *camera, Stream *stream,
			       std::vector<std::unique_ptr<FrameBuffer>> *buffers) override;

	int start(Camera *camera, const ControlList *controls) override;
	void stop(Camera *camera) override;

	int queueRequestDevice(Camera *camera, Request *request) override;

	bool match(DeviceEnumerator *enumerator) override;
};

PipelineHandlerVivid::PipelineHandlerVivid(CameraManager *manager)
	: PipelineHandler(manager)
{
}

CameraConfiguration *PipelineHandlerVivid::generateConfiguration(Camera *camera,
								 const StreamRoles &roles)
{
	return nullptr;
}

int PipelineHandlerVivid::configure(Camera *camera, CameraConfiguration *config)
{
	return -1;
}

int PipelineHandlerVivid::exportFrameBuffers(Camera *camera, Stream *stream,
					     std::vector<std::unique_ptr<FrameBuffer>> *buffers)
{
	return -1;
}

int PipelineHandlerVivid::start(Camera *camera, const ControlList *controls)
{
	return -1;
}

void PipelineHandlerVivid::stop(Camera *camera)
{
}

int PipelineHandlerVivid::queueRequestDevice(Camera *camera, Request *request)
{
	return -1;
}

bool PipelineHandlerVivid::match(DeviceEnumerator *enumerator)
{
	return false;
}

REGISTER_PIPELINE_HANDLER(PipelineHandlerVivid)

} /* namespace libcamera */
