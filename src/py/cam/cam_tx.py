# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2023, Tomi Valkeinen <tomi.valkeinen@ideasonboard.com>

import argparse
import libcamera
import libcamera.utils
import selectors
import socket
import struct
import sys

PORT = 43242

# ctx-idx, width, height, format, num-planes, plane1, plane2, plane3, plane4
struct_fmt = struct.Struct('<III12pI4I')


class TxRenderer:
    def __init__(self, state, ropts):
        parser = argparse.ArgumentParser(prog='TxRenderer')
        parser.add_argument('host', default='localhost', help='Address')
        args = parser.parse_args(ropts.split(' '))

        self.host = args.host

        self.state = state

        self.cm = state.cm
        self.contexts = state.contexts

        self.running = False

    def setup(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((self.host, PORT))
        self.sock = sock

        buf_mmap_map = {}

        for ctx in self.contexts:
            for stream in ctx.streams:
                for buf in ctx.allocator.buffers(stream):
                    mfb = libcamera.utils.MappedFrameBuffer(buf).mmap()
                    buf_mmap_map[buf] = mfb

        self.buf_mmap_map = buf_mmap_map

    def run(self):
        print('Capturing...')

        self.running = True

        sel = selectors.DefaultSelector()
        sel.register(self.cm.event_fd, selectors.EVENT_READ, self.readcam)
        sel.register(sys.stdin, selectors.EVENT_READ, self.readkey)

        print('Press enter to exit')

        while self.running:
            events = sel.select()
            for key, _ in events:
                callback = key.data
                callback(key.fileobj)

        print('Exiting...')

    def readcam(self, fd):
        self.running = self.state.event_handler()

    def readkey(self, fileobj):
        sys.stdin.readline()
        self.running = False

    def request_handler(self, ctx, req):
        buffers = req.buffers

        for stream, fb in buffers.items():
            mfb = self.buf_mmap_map[fb]

            plane_sizes = [len(p) for p in mfb.planes] + [0] * (4 - len(mfb.planes))

            stream_config = stream.configuration

            hdr = struct_fmt.pack(ctx.idx,
                                  stream_config.size.width, stream_config.size.height,
                                  bytes(str(stream_config.pixel_format), 'ascii'),
                                  len(mfb.planes), *plane_sizes)

            self.sock.sendall(hdr)

            for p in mfb.planes:
                self.sock.sendall(p)

        self.state.request_processed(ctx, req)
