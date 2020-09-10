#!/usr/bin/python3

import pycamera as pycam
import time
import binascii
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("-n", "--num-frames", type=int, default=10)
parser.add_argument("-c", "--print-crc", action="store_true")
parser.add_argument("-s", "--save-frames", action="store_true")
parser.add_argument("-m", "--max-cameras", type=int)
args = parser.parse_args()

cm = pycam.CameraManager()

cameras = cm.cameras

if len(cameras) == 0:
	print("No cameras")
	exit(0)

print("Cameras:")
for c in cameras:
	print("    {}".format(c.id))

contexts = []

for i in range(len(cameras)):
	contexts.append({ "camera": cameras[i], "id": i })
	if args.max_cameras and args.max_cameras - 1 == i:
		break

for ctx in contexts:
	ctx["camera"].acquire()

def configure_camera(ctx):
	camera = ctx["camera"]

	# Configure

	config = camera.generateConfiguration([pycam.StreamRole.Viewfinder])
	stream_config = config.at(0)

	#stream_config.width = 160;
	#stream_config.height = 120;
	#stream_config.fmt = "YUYV"

	print("Cam {}: stream config {}".format(ctx["id"], stream_config.toString()))

	camera.configure(config);

	# Allocate buffers

	stream = stream_config.stream

	allocator = pycam.FrameBufferAllocator(camera);
	ret = allocator.allocate(stream)
	if ret < 0:
		print("Can't allocate buffers")
		exit(-1)

	allocated = allocator.num_buffers(stream)
	print("Cam {}: Allocated {} buffers for stream".format(ctx["id"], allocated))

	# Create Requests

	requests = []
	buffers = allocator.buffers(stream)

	for buffer in buffers:
		request = camera.createRequest()
		if request == None:
			print("Can't create request")
			exit(-1)

		ret = request.addBuffer(stream, buffer)
		if ret < 0:
			print("Can't set buffer for request")
			exit(-1)

		requests.append(request)

	ctx["allocator"] = allocator
	ctx["requests"] = requests


def buffer_complete_cb(ctx, req, fb):
	print("Cam {}: Buf {} Complete: {}".format(ctx["id"], ctx["bufs_completed"], req.status))

	with fb.mmap(0) as b:
		if args.print_crc:
			crc = binascii.crc32(b)
			print("Cam {}:    CRC {:#x}".format(ctx["id"], crc))

		if args.save_frames:
			id = ctx["id"]
			num = ctx["bufs_completed"]
			filename = "frame-{}-{}.data".format(id, num)
			with open(filename, "wb") as f:
				f.write(b)
			print("Cam {}:    Saved {}".format(ctx["id"], filename))

	ctx["bufs_completed"] += 1

def req_complete_cb(ctx, req):
	camera = ctx["camera"]

	print("Cam {}: Req {} Complete: {}".format(ctx["id"], ctx["reqs_completed"], req.status))

	bufs = req.buffers
	for stream, fb in bufs.items():
		meta = fb.metadata
		print("Cam {}: Buf seq {}, bytes {}".format(ctx["id"], meta.sequence, meta.bytesused(0)))

	ctx["reqs_completed"] += 1

	if ctx["reqs_queued"] < args.num_frames:
		request = camera.createRequest()
		if request == None:
			print("Can't create request")
			exit(-1)

		for stream, fb in bufs.items():
			ret = request.addBuffer(stream, fb)
			if ret < 0:
				print("Can't set buffer for request")
				exit(-1)

		camera.queueRequest(request)
		ctx["reqs_queued"] += 1


def setup_callbacks(ctx):
	camera = ctx["camera"]

	ctx["reqs_queued"] = 0
	ctx["reqs_completed"] = 0
	ctx["bufs_completed"] = 0

	camera.requestCompleted = lambda req, ctx = ctx: req_complete_cb(ctx, req)
	camera.bufferCompleted = lambda req, fb, ctx = ctx: buffer_complete_cb(ctx, req, fb)

def queue_requests(ctx):
	camera = ctx["camera"]
	requests = ctx["requests"]

	camera.start()

	for request in requests:
		camera.queueRequest(request)
		ctx["reqs_queued"] += 1



for ctx in contexts:
	configure_camera(ctx)
	setup_callbacks(ctx)

for ctx in contexts:
	queue_requests(ctx)


print("Processing...")

# Need to release GIL here, so that callbacks can be called
while any(ctx["reqs_completed"] < args.num_frames for ctx in contexts):
	pycam.sleep(0.1)

print("Exiting...")

for ctx in contexts:
	camera = ctx["camera"]
	camera.stop()
	camera.release()

print("Done")
