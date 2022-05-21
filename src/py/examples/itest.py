#!/usr/bin/env python3

# SPDX-License-Identifier: BSD-3-Clause
# Copyright (C) 2022, Tomi Valkeinen <tomi.valkeinen@ideasonboard.com>

# This sets up a single camera, starts a capture loop in a background thread,
# and starts an IPython shell which can be used to study and test libcamera.
#
# Note: This is not an example as such, but more of a developer tool to try
# out things.

import argparse
import IPython
import libcamera as libcam
import selectors
import sys
import threading


def handle_camera_event(ctx):
    cm = ctx['cm']
    cam = ctx['cam']

    # cm.get_ready_requests() will not block here, as we know there is an event
    # to read.

    reqs = cm.get_ready_requests()

    assert len(reqs) > 0

    # Process the captured frames

    for req in reqs:
        buffers = req.buffers

        assert len(buffers) == 1

        # We want to re-queue the buffer we just handled. Instead of creating
        # a new Request, we re-use the old one. We need to call req.reuse()
        # to re-initialize the Request before queuing.

        req.reuse()
        cam.queue_request(req)

        scope = ctx['scope']

        if 'num_frames' not in scope:
            scope['num_frames'] = 0

        scope['num_frames'] += 1


def capture(ctx):
    cm = ctx['cm']
    cam = ctx['cam']
    reqs = ctx['reqs']

    # Queue the requests to the camera

    for req in reqs:
        ret = cam.queue_request(req)
        assert ret == 0

    # Use Selector to wait for events from the camera and from the keyboard

    sel = selectors.DefaultSelector()
    sel.register(cm.event_fd, selectors.EVENT_READ, lambda fd: handle_camera_event(ctx))

    reqs = []

    while ctx['running']:
        events = sel.select()
        for key, mask in events:
            key.data(key.fileobj)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--camera', type=str, default='1',
                        help='Camera index number (starting from 1) or part of the name')
    parser.add_argument('-f', '--format', type=str, help='Pixel format')
    parser.add_argument('-s', '--size', type=str, help='Size ("WxH")')
    args = parser.parse_args()

    cm = libcam.CameraManager.singleton()

    try:
        if args.camera.isnumeric():
            cam_idx = int(args.camera)
            cam = next((cam for i, cam in enumerate(cm.cameras) if i + 1 == cam_idx))
        else:
            cam = next((cam for cam in cm.cameras if args.camera in cam.id))
    except Exception:
        print(f'Failed to find camera "{args.camera}"')
        return -1

    # Acquire the camera for our use

    ret = cam.acquire()
    assert ret == 0

    # Configure the camera

    cam_config = cam.generate_configuration([libcam.StreamRole.Viewfinder])

    stream_config = cam_config.at(0)

    if args.format:
        fmt = libcam.PixelFormat(args.format)
        stream_config.pixel_format = fmt

    if args.size:
        w, h = [int(v) for v in args.size.split('x')]
        stream_config.size = libcam.Size(w, h)

    ret = cam.configure(cam_config)
    assert ret == 0

    stream = stream_config.stream

    # Allocate the buffers for capture

    allocator = libcam.FrameBufferAllocator(cam)
    ret = allocator.allocate(stream)
    assert ret > 0

    num_bufs = len(allocator.buffers(stream))

    print(f'Capturing {stream_config} with {num_bufs} buffers from {cam.id}')

    # Create the requests and assign a buffer for each request

    reqs = []
    for i in range(num_bufs):
        # Use the buffer index as the "cookie"
        req = cam.create_request(i)

        buffer = allocator.buffers(stream)[i]
        ret = req.add_buffer(stream, buffer)
        assert ret == 0

        reqs.append(req)

    # Start the camera

    ret = cam.start()
    assert ret == 0

    # Create a scope for the IPython shell
    scope = {
        'cm': cm,
        'cam': cam,
        'libcam': libcam,
    }

    # Create a simple context shared between the background thread and the main
    # thread.
    ctx = {
        'running': True,
        'cm': cm,
        'cam': cam,
        'reqs': reqs,
        'scope': scope,
    }

    # Note that "In CPython, due to the Global Interpreter Lock, only one thread
    # can execute Python code at once". We rely on that here, which is not very
    # nice. I am sure an fd-based polling loop could be integrated with IPython,
    # somehow, which would allow us to drop the threading.

    t = threading.Thread(target=capture, args=(ctx,))
    t.start()

    IPython.embed(banner1='', exit_msg='', confirm_exit=False, user_ns=scope)

    print('Exiting...')

    ctx['running'] = False
    t.join()

    # Stop the camera

    ret = cam.stop()
    assert ret == 0

    # Release the camera

    ret = cam.release()
    assert ret == 0

    return 0


if __name__ == '__main__':
    sys.exit(main())
