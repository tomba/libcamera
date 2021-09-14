#!/usr/bin/python3

import pycamera as pycam
import selectors
import os
import unittest
import gc
from collections import defaultdict
import time
import selectors
import os

class SimpleTestMethods(unittest.TestCase):
	def test_find_ref(self):
		cm = pycam.CameraManager.singleton()
		cam = cm.find("platform/vimc")
		self.assertTrue(cam != None)
		gc.collect()
		# Should cause libcamera WARN/ERROR or crash if cam -> cm keep_alive doesn't work

	def test_get_ref(self):
		cm = pycam.CameraManager.singleton()
		cam = cm.get("platform/vimc.0 Sensor B")
		self.assertTrue(cam != None)
		gc.collect()
		# Should cause libcamera WARN/ERROR or crash if cam -> cm keep_alive doesn't work

class SimpleCaptureMethods(unittest.TestCase):

	def setUp(self):
		self.cm = pycam.CameraManager.singleton()
		self.cam = self.cm.find("platform/vimc")
		if self.cam == None:
			self.cm = None
			raise Exception("No vimc found")

		r = self.cam.acquire()
		if r != 0:
			self.cam = None
			self.cm = None
			raise Exception("Failed to acquire camera")


	def tearDown(self):
		self.cam.release()

	def test_sleep(self):
		cm = self.cm
		cam = self.cam

		camconfig = cam.generateConfiguration([pycam.StreamRole.StillCapture])
		self.assertTrue(camconfig.size == 1)

		streamconfig = camconfig.at(0)
		fmts = streamconfig.formats

		ret = cam.configure(camconfig);
		self.assertTrue(ret == 0)

		stream = streamconfig.stream

		allocator = pycam.FrameBufferAllocator(cam);
		ret = allocator.allocate(stream)
		self.assertTrue(ret > 0)

		num_bufs = len(allocator.buffers(stream))

		reqs = []
		for i in range(num_bufs):
			req = cam.createRequest(i)

			buffer = allocator.buffers(stream)[i]
			ret = req.addBuffer(stream, buffer)
			self.assertTrue(ret == 0)

			reqs.append(req)

		buffer = None

		cam.start()

		for req in reqs:
			cam.queueRequest(req)

		reqs = None
		gc.collect()

		time.sleep(0.5)

		reqs = cm.get_ready_requests()

		self.assertTrue(len(reqs) == num_bufs)

		for i, req in enumerate(reqs):
			self.assertTrue(i == req.cookie)

		reqs = None
		gc.collect()

		cam.stop()


	def test_select(self):
		cm = self.cm
		cam = self.cam

		camconfig = cam.generateConfiguration([pycam.StreamRole.StillCapture])
		self.assertTrue(camconfig.size == 1)

		streamconfig = camconfig.at(0)
		fmts = streamconfig.formats

		ret = cam.configure(camconfig);
		self.assertTrue(ret == 0)

		stream = streamconfig.stream

		allocator = pycam.FrameBufferAllocator(cam);
		ret = allocator.allocate(stream)
		self.assertTrue(ret > 0)

		num_bufs = len(allocator.buffers(stream))

		reqs = []
		for i in range(num_bufs):
			req = cam.createRequest(i)

			buffer = allocator.buffers(stream)[i]
			ret = req.addBuffer(stream, buffer)
			self.assertTrue(ret == 0)

			reqs.append(req)

		buffer = None

		cam.start()

		for req in reqs:
			cam.queueRequest(req)

		reqs = None
		gc.collect()

		sel = selectors.DefaultSelector()
		sel.register(cm.efd, selectors.EVENT_READ, 123)

		reqs = []

		running = True
		while running:
			events = sel.select()
			for key, mask in events:
				data = os.read(key.fileobj, 8)

				l = cm.get_ready_requests()

				self.assertTrue(len(l) > 0)

				reqs += l

				if len(reqs) == num_bufs:
					running = False

		self.assertTrue(len(reqs) == num_bufs)

		for i, req in enumerate(reqs):
			self.assertTrue(i == req.cookie)

		reqs = None
		gc.collect()

		cam.stop()


if __name__ == '__main__':
	before = defaultdict(int)
	after = defaultdict(int)
	for i in gc.get_objects():
		before[type(i)] += 1

	unittest.main()

	for i in gc.get_objects():
		after[type(i)] += 1

	leaks = [(k, after[k] - before[k]) for k in after if after[k] - before[k]]
	if len(leaks) > 0:
		print(leaks)
