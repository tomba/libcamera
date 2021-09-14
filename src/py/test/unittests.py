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
import errno

class MyTestCase(unittest.TestCase):
	def assertZero(self, a, msg=None):
		self.assertEqual(a, 0, msg)

class SimpleTestMethods(MyTestCase):
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

	def test_acquire_release(self):
		cm = pycam.CameraManager.singleton()
		cam = cm.get("platform/vimc.0 Sensor B")
		self.assertTrue(cam != None)

		ret = cam.acquire()
		self.assertZero(ret)

		ret = cam.release()
		self.assertZero(ret)

	def test_double_acquire(self):
		cm = pycam.CameraManager.singleton()
		cam = cm.get("platform/vimc.0 Sensor B")
		self.assertTrue(cam != None)

		ret = cam.acquire()
		self.assertZero(ret)

		pycam.logSetLevel("Camera", "FATAL")
		ret = cam.acquire()
		self.assertEqual(ret, -errno.EBUSY)
		pycam.logSetLevel("Camera", "ERROR")

		ret = cam.release()
		self.assertZero(ret)

		ret = cam.release()
		# I expected EBUSY, but looks like double release works fine
		self.assertZero(ret)



class SimpleCaptureMethods(MyTestCase):

	def setUp(self):
		self.cm = pycam.CameraManager.singleton()
		self.cam = self.cm.find("platform/vimc")
		if self.cam == None:
			self.cm = None
			raise Exception("No vimc found")

		ret = self.cam.acquire()
		if ret != 0:
			self.cam = None
			self.cm = None
			raise Exception("Failed to acquire camera")


	def tearDown(self):
		# If a test fails, the camera may be in running state. So always stop.
		self.cam.stop()

		ret = self.cam.release()
		if ret != 0:
			raise Exception("Failed to release camera")

		self.cam = None
		self.cm = None

	def test_sleep(self):
		cm = self.cm
		cam = self.cam

		camconfig = cam.generateConfiguration([pycam.StreamRole.StillCapture])
		self.assertTrue(camconfig.size == 1)

		streamconfig = camconfig.at(0)
		fmts = streamconfig.formats

		ret = cam.configure(camconfig);
		self.assertZero(ret)

		stream = streamconfig.stream

		allocator = pycam.FrameBufferAllocator(cam);
		ret = allocator.allocate(stream)
		self.assertTrue(ret > 0)

		num_bufs = len(allocator.buffers(stream))

		reqs = []
		for i in range(num_bufs):
			req = cam.createRequest(i)
			self.assertIsNotNone(req)

			buffer = allocator.buffers(stream)[i]
			ret = req.addBuffer(stream, buffer)
			self.assertZero(ret)

			reqs.append(req)

		buffer = None

		ret = cam.start()
		self.assertZero(ret)

		for req in reqs:
			ret = cam.queueRequest(req)
			self.assertZero(ret)

		reqs = None
		gc.collect()

		time.sleep(0.5)

		reqs = cm.getReadyRequests()

		self.assertTrue(len(reqs) == num_bufs)

		for i, req in enumerate(reqs):
			self.assertTrue(i == req.cookie)

		reqs = None
		gc.collect()

		ret = cam.stop()
		self.assertZero(ret)


	def test_select(self):
		cm = self.cm
		cam = self.cam

		camconfig = cam.generateConfiguration([pycam.StreamRole.StillCapture])
		self.assertTrue(camconfig.size == 1)

		streamconfig = camconfig.at(0)
		fmts = streamconfig.formats

		ret = cam.configure(camconfig);
		self.assertZero(ret)

		stream = streamconfig.stream

		allocator = pycam.FrameBufferAllocator(cam);
		ret = allocator.allocate(stream)
		self.assertTrue(ret > 0)

		num_bufs = len(allocator.buffers(stream))

		reqs = []
		for i in range(num_bufs):
			req = cam.createRequest(i)
			self.assertIsNotNone(req)

			buffer = allocator.buffers(stream)[i]
			ret = req.addBuffer(stream, buffer)
			self.assertZero(ret)

			reqs.append(req)

		buffer = None

		ret = cam.start()
		self.assertZero(ret)

		for req in reqs:
			ret = cam.queueRequest(req)
			self.assertZero(ret)

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

				l = cm.getReadyRequests()

				self.assertTrue(len(l) > 0)

				reqs += l

				if len(reqs) == num_bufs:
					running = False

		self.assertTrue(len(reqs) == num_bufs)

		for i, req in enumerate(reqs):
			self.assertTrue(i == req.cookie)

		reqs = None
		gc.collect()

		ret = cam.stop()
		self.assertZero(ret)


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
