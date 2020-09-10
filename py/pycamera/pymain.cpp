#include <chrono>
#include <thread>
#include <fcntl.h>
#include <unistd.h>
#include <sys/mman.h>

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/stl_bind.h>
#include <pybind11/functional.h>

#include <libcamera/libcamera.h>

namespace py = pybind11;

using namespace std;
using namespace libcamera;

PYBIND11_MODULE(pycamera, m) {
	m.def("sleep", [](double s) {
		py::gil_scoped_release release;
		this_thread::sleep_for(std::chrono::duration<double>(s));
	});

	py::class_<CameraManager>(m, "CameraManager")
			// Call cm->start implicitly, as we can't use stop() either
			.def(py::init([]() {
				auto cm = make_unique<CameraManager>();
				cm->start();
				return cm;
			}))

			//.def("start", &CameraManager::start)

			// stop() cannot be called, as CameraManager expects all Camera instances to be released before calling stop
			// and we can't have such requirement in python, especially as we have a keep-alive from Camera to CameraManager.
			// So we rely on GC and the keep-alives.
			//.def("stop", &CameraManager::stop)

			.def_property_readonly("num_cameras", [](CameraManager& cm) { return cm.cameras().size(); })
			.def("at", [](CameraManager& cm, unsigned int idx) { return cm.cameras()[idx]; }, py::keep_alive<0, 1>())
	;

	py::class_<Camera, shared_ptr<Camera>>(m, "Camera")
			.def_property_readonly("id", &Camera::id)
			.def("acquire", &Camera::acquire)
			.def("release", &Camera::release)
			.def("start", &Camera::start)
			.def("stop", [](shared_ptr<Camera>& self) {
				// Camera::stop can cause callbacks to be invoked, so we must release GIL
				py::gil_scoped_release release;
				self->stop();
			})
			.def("generateConfiguration", &Camera::generateConfiguration)
			.def("configure", &Camera::configure)

			// XXX created requests MUST be queued to be freed, python will not free them
			.def("createRequest", &Camera::createRequest, py::arg("cookie") = 0, py::return_value_policy::reference_internal)
			.def("queueRequest", &Camera::queueRequest)

			.def_property("requestCompleted",
				      nullptr,
				      [](shared_ptr<Camera>& self, function<void(Request*)> f) {
						if (f) {
							self->requestCompleted.connect(function<void(Request*)>([f = move(f)](Request* req) {
								// Called from libcamera's internal thread, so need to get GIL
								py::gil_scoped_acquire acquire;
								f(req);
							}));
						} else {
							// XXX Disconnects all, as we have no means to disconnect the specific std::function
							self->requestCompleted.disconnect();
						}
					}
			)

			.def_property("bufferCompleted",
				      nullptr,
				      [](shared_ptr<Camera>& self, function<void(Request*, FrameBuffer*)> f) {
						if (f) {
							self->bufferCompleted.connect(function<void(Request*, FrameBuffer* fb)>([f = move(f)](Request* req, FrameBuffer* fb) {
								// Called from libcamera's internal thread, so need to get GIL
								py::gil_scoped_acquire acquire;
								f(req, fb);
							}));
						} else {
							// XXX Disconnects all, as we have no means to disconnect the specific std::function
							self->bufferCompleted.disconnect();
						}
					}
			)

			;

	py::class_<CameraConfiguration>(m, "CameraConfiguration")
			.def("at", (StreamConfiguration& (CameraConfiguration::*)(unsigned int))&CameraConfiguration::at,
			     py::return_value_policy::reference_internal)
			.def("validate", &CameraConfiguration::validate)
			.def_property_readonly("size", &CameraConfiguration::size)
			.def_property_readonly("empty", &CameraConfiguration::empty)
			;

	py::class_<StreamConfiguration>(m, "StreamConfiguration")
			.def("toString", &StreamConfiguration::toString)
			.def_property_readonly("stream", &StreamConfiguration::stream,
			     py::return_value_policy::reference_internal)
			.def_property("width",
				[](StreamConfiguration& c) { return c.size.width; },
				[](StreamConfiguration& c, unsigned int w) { c.size.width = w; }
			)
			.def_property("height",
				[](StreamConfiguration& c) { return c.size.height; },
				[](StreamConfiguration& c, unsigned int h) { c.size.height = h; }
			)
			.def_property("fmt",
				[](StreamConfiguration& c) { return c.pixelFormat.toString(); },
				[](StreamConfiguration& c, string fmt) { c.pixelFormat = PixelFormat::fromString(fmt); }
			)
			;

	py::enum_<StreamRole>(m, "StreamRole")
			.value("StillCapture", StreamRole::StillCapture)
			.value("StillCaptureRaw", StreamRole::StillCaptureRaw)
			.value("VideoRecording", StreamRole::VideoRecording)
			.value("Viewfinder", StreamRole::Viewfinder)
			;

	py::class_<FrameBufferAllocator>(m, "FrameBufferAllocator")
			.def(py::init<shared_ptr<Camera>>(), py::keep_alive<1, 2>())
			.def("allocate", &FrameBufferAllocator::allocate)
			.def("free", &FrameBufferAllocator::free)
			.def("num_buffers", [](FrameBufferAllocator& fa, Stream* stream) { return fa.buffers(stream).size(); })
			.def("at", [](FrameBufferAllocator& fa, Stream* stream, unsigned int idx) { return fa.buffers(stream).at(idx).get(); },
				py::return_value_policy::reference_internal)
			;

	py::class_<FrameBuffer, unique_ptr<FrameBuffer, py::nodelete>>(m, "FrameBuffer")
			.def_property_readonly("metadata", &FrameBuffer::metadata, py::return_value_policy::reference_internal)
			.def("length", [](FrameBuffer& fb, uint32_t idx) {
				const FrameBuffer::Plane &plane = fb.planes()[idx];
				return plane.length;
			})
			.def("fd", [](FrameBuffer& fb, uint32_t idx) {
				const FrameBuffer::Plane &plane = fb.planes()[idx];
				return plane.fd.fd();
			})
			;

	py::class_<Stream, unique_ptr<Stream, py::nodelete>>(m, "Stream")
			;

	py::class_<Request, unique_ptr<Request, py::nodelete>>(m, "Request")
			.def("addBuffer", &Request::addBuffer)
			.def_property_readonly("status", &Request::status)
			.def_property_readonly("buffers", &Request::buffers)
			;


	py::enum_<Request::Status>(m, "RequestStatus")
			.value("Pending", Request::RequestPending)
			.value("Complete", Request::RequestComplete)
			.value("Cancelled", Request::RequestCancelled)
			;

	py::class_<FrameMetadata>(m, "FrameMetadata")
			.def_property_readonly("sequence", [](FrameMetadata& data) { return data.sequence; })
			.def("bytesused", [](FrameMetadata& data, uint32_t idx) { return data.planes[idx].bytesused; })
			;
}
