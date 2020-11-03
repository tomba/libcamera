/* SPDX-License-Identifier: LGPL-2.1-or-later */
/*
 * Copyright (C) 2020, Google Inc.
 *
 * vivid.cpp - Pipeline handler for the vivid capture device
 */

#include <math.h>

#include <libcamera/base/log.h>

#include <libcamera/camera.h>
#include <libcamera/control_ids.h>
#include <libcamera/controls.h>
#include <libcamera/formats.h>
#include <libcamera/property_ids.h>

#include "libcamera/internal/camera.h"
#include "libcamera/internal/device_enumerator.h"
#include "libcamera/internal/media_device.h"
#include "libcamera/internal/pipeline_handler.h"
#include "libcamera/internal/v4l2_videodevice.h"

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

#define VIVID_CID_VIVID_BASE            (0x00f00000 | 0xf000)
#define VIVID_CID_VIVID_CLASS           (0x00f00000 | 1)
#define VIVID_CID_TEST_PATTERN          (VIVID_CID_VIVID_BASE + 0)
#define VIVID_CID_OSD_TEXT_MODE         (VIVID_CID_VIVID_BASE + 1)
#define VIVID_CID_HOR_MOVEMENT          (VIVID_CID_VIVID_BASE + 2)
#define VIVID_CID_VERT_MOVEMENT         (VIVID_CID_VIVID_BASE + 3)
#define VIVID_CID_SHOW_BORDER           (VIVID_CID_VIVID_BASE + 4)
#define VIVID_CID_SHOW_SQUARE           (VIVID_CID_VIVID_BASE + 5)
#define VIVID_CID_INSERT_SAV            (VIVID_CID_VIVID_BASE + 6)
#define VIVID_CID_INSERT_EAV            (VIVID_CID_VIVID_BASE + 7)
#define VIVID_CID_VBI_CAP_INTERLACED    (VIVID_CID_VIVID_BASE + 8)

namespace libcamera {

LOG_DEFINE_CATEGORY(VIVID)

class VividCameraData : public Camera::Private
{
public:
	VividCameraData(PipelineHandler *pipe, MediaDevice *media)
		: Camera::Private(pipe), media_(media), video_(nullptr)
	{
	}

	~VividCameraData()
	{
		delete video_;
	}

	int init();
	void bufferReady(FrameBuffer *buffer);

	MediaDevice *media_;
	V4L2VideoDevice *video_;
	Stream stream_;
};

class VividCameraConfiguration : public CameraConfiguration
{
public:
	VividCameraConfiguration();

	Status validate() override;
};

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

private:
	int processControls(VividCameraData *data, Request *request);

	VividCameraData *cameraData(Camera *camera)
	{
		return static_cast<VividCameraData *>(camera->_d());
	}
};

VividCameraConfiguration::VividCameraConfiguration()
	: CameraConfiguration()
{
}

CameraConfiguration::Status VividCameraConfiguration::validate()
{
	Status status = Valid;

	if (config_.empty())
		return Invalid;

	/* Cap the number of entries to the available streams. */
	if (config_.size() > 1) {
		config_.resize(1);
		status = Adjusted;
	}

	StreamConfiguration &cfg = config_[0];

	/* Adjust the pixel format. */
	const std::vector<libcamera::PixelFormat> formats = cfg.formats().pixelformats();
	if (std::find(formats.begin(), formats.end(), cfg.pixelFormat) == formats.end()) {
		cfg.pixelFormat = cfg.formats().pixelformats()[0];
		LOG(VIVID, Debug) << "Adjusting format to " << cfg.pixelFormat.toString();
		status = Adjusted;
	}

	cfg.bufferCount = 4;

	return status;
}

PipelineHandlerVivid::PipelineHandlerVivid(CameraManager *manager)
	: PipelineHandler(manager)
{
}

CameraConfiguration *PipelineHandlerVivid::generateConfiguration(Camera *camera,
								 const StreamRoles &roles)
{
	CameraConfiguration *config = new VividCameraConfiguration();
	VividCameraData *data = cameraData(camera);

	if (roles.empty())
		return config;

	std::map<V4L2PixelFormat, std::vector<SizeRange>> v4l2Formats =
		data->video_->formats();
	std::map<PixelFormat, std::vector<SizeRange>> deviceFormats;
	std::transform(v4l2Formats.begin(), v4l2Formats.end(),
		       std::inserter(deviceFormats, deviceFormats.begin()),
		       [&](const decltype(v4l2Formats)::value_type &format) {
			       return decltype(deviceFormats)::value_type{
				       format.first.toPixelFormat(),
				       format.second
			       };
		       });

	StreamFormats formats(deviceFormats);
	StreamConfiguration cfg(formats);

	cfg.pixelFormat = formats::BGR888;
	cfg.size = { 1280, 720 };
	cfg.bufferCount = 4;

	config->addConfiguration(cfg);

	config->validate();

	return config;
}

int PipelineHandlerVivid::configure(Camera *camera, CameraConfiguration *config)
{
	VividCameraData *data = cameraData(camera);
	StreamConfiguration &cfg = config->at(0);
	int ret;

	V4L2DeviceFormat format = {};
	format.fourcc = V4L2PixelFormat::fromPixelFormat(cfg.pixelFormat);
	format.size = cfg.size;

	ret = data->video_->setFormat(&format);
	if (ret)
		return ret;

	if (format.size != cfg.size ||
	    format.fourcc != V4L2PixelFormat::fromPixelFormat(cfg.pixelFormat)) {
		LOG(VIVID, Error)
			<< "Requested " << cfg.toString() << ", got "
			<< format.size.toString() << "-"
			<< format.fourcc.toString();
		return -EINVAL;
	}

	/* Set initial controls specific to VIVID */
	ControlList controls(data->video_->controls());
	controls.set(VIVID_CID_TEST_PATTERN, 0); /* Vertical Colour Bars */
	controls.set(VIVID_CID_OSD_TEXT_MODE, 0); /* Display all OSD */

	/* Ensure clear colours configured. */
	controls.set(V4L2_CID_BRIGHTNESS, 128);
	controls.set(V4L2_CID_CONTRAST, 128);
	controls.set(V4L2_CID_SATURATION, 128);

	/* Enable movement to visualise buffer updates. */
	controls.set(VIVID_CID_HOR_MOVEMENT, 5);

	ret = data->video_->setControls(&controls);
	if (ret) {
		LOG(VIVID, Error) << "Failed to set controls: " << ret;
		return ret < 0 ? ret : -EINVAL;
	}

	cfg.setStream(&data->stream_);
	cfg.stride = format.planes[0].bpl;

	return 0;
}

int PipelineHandlerVivid::exportFrameBuffers(Camera *camera, Stream *stream,
					     std::vector<std::unique_ptr<FrameBuffer>> *buffers)
{
	VividCameraData *data = cameraData(camera);
	unsigned int count = stream->configuration().bufferCount;

	return data->video_->exportBuffers(count, buffers);
}

int PipelineHandlerVivid::start(Camera *camera, const ControlList *controls)
{
	VividCameraData *data = cameraData(camera);
	unsigned int count = data->stream_.configuration().bufferCount;

	int ret = data->video_->importBuffers(count);
	if (ret < 0)
		return ret;

	ret = data->video_->streamOn();
	if (ret < 0) {
		data->video_->releaseBuffers();
		return ret;
	}

	return 0;
}

void PipelineHandlerVivid::stop(Camera *camera)
{
	VividCameraData *data = cameraData(camera);
	data->video_->streamOff();
	data->video_->releaseBuffers();
}

int PipelineHandlerVivid::processControls(VividCameraData *data, Request *request)
{
	ControlList controls(data->video_->controls());

	for (auto it : request->controls()) {
		unsigned int id = it.first;
		unsigned int offset;
		uint32_t cid;

		if (id == controls::Brightness) {
			cid = V4L2_CID_BRIGHTNESS;
			offset = 128;
		} else if (id == controls::Contrast) {
			cid = V4L2_CID_CONTRAST;
			offset = 0;
		} else if (id == controls::Saturation) {
			cid = V4L2_CID_SATURATION;
			offset = 0;
		} else {
			continue;
		}

		int32_t value = lroundf(it.second.get<float>() * 128 + offset);
		controls.set(cid, std::clamp(value, 0, 255));
	}

	for (const auto &ctrl : controls)
		LOG(VIVID, Debug)
			<< "Setting control " << utils::hex(ctrl.first)
			<< " to " << ctrl.second.toString();

	int ret = data->video_->setControls(&controls);
	if (ret) {
		LOG(VIVID, Error) << "Failed to set controls: " << ret;
		return ret < 0 ? ret : -EINVAL;
	}

	return ret;
}

int PipelineHandlerVivid::queueRequestDevice(Camera *camera, Request *request)
{
	VividCameraData *data = cameraData(camera);
	FrameBuffer *buffer = request->findBuffer(&data->stream_);
	if (!buffer) {
		LOG(VIVID, Error)
			<< "Attempt to queue request with invalid stream";

		return -ENOENT;
	}

	int ret = processControls(data, request);
	if (ret < 0)
		return ret;

	ret = data->video_->queueBuffer(buffer);
	if (ret < 0)
		return ret;

	return 0;
}

bool PipelineHandlerVivid::match(DeviceEnumerator *enumerator)
{
	DeviceMatch dm("vivid");
	dm.add("vivid-000-vid-cap");

	MediaDevice *media = acquireMediaDevice(enumerator, dm);
	if (!media)
		return false;

	std::unique_ptr<VividCameraData> data = std::make_unique<VividCameraData>(this, media);

	/* Locate and open the capture video node. */
	if (data->init())
		return false;

	/* Create and register the camera. */
	std::set<Stream *> streams{ &data->stream_ };
	const std::string id = data->video_->deviceName();
	std::shared_ptr<Camera> camera = Camera::create(std::move(data), id, streams);
	registerCamera(std::move(camera));

	return true;
}

int VividCameraData::init()
{
	video_ = new V4L2VideoDevice(media_->getEntityByName("vivid-000-vid-cap"));
	if (video_->open())
		return -ENODEV;

	video_->bufferReady.connect(this, &VividCameraData::bufferReady);

	/* Initialise the supported controls and properties. */
	const ControlInfoMap &controls = video_->controls();
	ControlInfoMap::Map ctrls;

	for (const auto &ctrl : controls) {
		const ControlId *id;
		ControlInfo info;

		switch (ctrl.first->id()) {
		case V4L2_CID_BRIGHTNESS:
			id = &controls::Brightness;
			info = ControlInfo{ { -1.0f }, { 1.0f }, { 0.0f } };
			break;
		case V4L2_CID_CONTRAST:
			id = &controls::Contrast;
			info = ControlInfo{ { 0.0f }, { 2.0f }, { 1.0f } };
			break;
		case V4L2_CID_SATURATION:
			id = &controls::Saturation;
			info = ControlInfo{ { 0.0f }, { 2.0f }, { 1.0f } };
			break;
		default:
			continue;
		}

		ctrls.emplace(id, info);
	}

	controlInfo_ = ControlInfoMap(std::move(ctrls), controls::controls);

	properties_.set(properties::Location, properties::CameraLocationExternal);
	properties_.set(properties::Model, "Virtual Video Device");

	return 0;
}

void VividCameraData::bufferReady(FrameBuffer *buffer)
{
	Request *request = buffer->request();

	pipe()->completeBuffer(request, buffer);
	pipe()->completeRequest(request);
}

REGISTER_PIPELINE_HANDLER(PipelineHandlerVivid)

} /* namespace libcamera */
