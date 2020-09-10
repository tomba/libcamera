from .pycamera import *
from enum import Enum
import os
import struct
import mmap

# Add a wrapper which returns an array of Cameras, which have keep-alive to the CameraManager
def __CameraManager__cameras(self):
	cameras = []
	for i in range(self.num_cameras):
		cameras.append(self.at(i))
	return cameras


CameraManager.cameras = property(__CameraManager__cameras)

# Add a wrapper which returns an array of buffers, which have keep-alive to the FB allocator
def __FrameBufferAllocator__buffers(self, stream):
	buffers = []
	for i in range(self.num_buffers(stream)):
		buffers.append(self.at(stream, i))
	return buffers

FrameBufferAllocator.buffers = __FrameBufferAllocator__buffers

def __FrameBuffer__mmap(self, plane):
	return mmap.mmap(self.fd(plane), self.length(plane), mmap.MAP_SHARED, mmap.PROT_READ)

FrameBuffer.mmap = __FrameBuffer__mmap
