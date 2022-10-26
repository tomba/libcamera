#!/usr/bin/env python3

# SPDX-License-Identifier: BSD-3-Clause
# Copyright (C) 2022, Tomi Valkeinen <tomi.valkeinen@ideasonboard.com>

# A simple capture example with opencv. This is almost identical to
# simple-capture.py, except we use opencv to process and show the image.

import argparse
import cv2
import libcamera as libcam
import libcamera.utils
import numpy as np
import selectors
import sys

# Number of frames to capture
TOTAL_FRAMES = 100


def cartoonify(cvbuf):
    grayScaleImage = cv2.cvtColor(cvbuf, cv2.COLOR_BGR2GRAY)
    smoothGrayScale = cv2.medianBlur(grayScaleImage, 5)
    edgefied = cv2.adaptiveThreshold(smoothGrayScale, 255,
                                     cv2.ADAPTIVE_THRESH_MEAN_C,
                                     cv2.THRESH_BINARY, 9, 9)
    return edgefied


def libcam_to_cv(mfb: libcamera.utils.MappedFrameBuffer, cfg: libcam.StreamConfiguration):
    w = cfg.size.width
    h = cfg.size.height
    fmt = cfg.pixel_format

    data = np.array(mfb.planes[0], dtype=np.uint8)

    if fmt == libcam.formats.YUYV:
        # This is not correct, produces a bluish tint. I didn't find out
        # what kind of array opencv wants for YUYV.
        yuyv = data.reshape((h, w // 2 * 4))
        yuv = np.empty((h, w, 2), dtype=np.uint8)
        yuv[:, :, 0] = yuyv[:, 0::2]                    # Y
        yuv[:, :, 1] = yuyv[:, 1::2]                    # UV
        image = cv2.cvtColor(yuv, cv2.COLOR_YUV2RGB_YUYV)
    elif fmt == libcam.formats.RGB888:
        rgb = data.reshape((h, w, 3))
        rgb[:, :, [0, 1, 2]] = rgb[:, :, [2, 1, 0]]
        image = rgb
    elif fmt == libcam.formats.BGR888:
        rgb = data.reshape((h, w, 3))
        image = rgb
    elif fmt == libcam.formats.MJPEG:
        image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    else:
        raise Exception("Unsupported pixel format")

    return image


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

    print(f'Capturing {TOTAL_FRAMES} frames with {stream_config}')

    stream = stream_config.stream

    # Allocate the buffers for capture

    allocator = libcam.FrameBufferAllocator(cam)
    ret = allocator.allocate(stream)
    assert ret > 0

    num_bufs = len(allocator.buffers(stream))

    # Create the requests and assign a buffer for each request

    reqs = []
    for i in range(num_bufs):
        # Use the buffer index as the cookie
        req = cam.create_request(i)

        buffer = allocator.buffers(stream)[i]
        ret = req.add_buffer(stream, buffer)
        assert ret == 0

        reqs.append(req)

    # Start the camera

    ret = cam.start()
    assert ret == 0

    # frames_queued and frames_done track the number of frames queued and done

    frames_queued = 0
    frames_done = 0

    # Queue the requests to the camera

    for req in reqs:
        ret = cam.queue_request(req)
        assert ret == 0
        frames_queued += 1

    # The main loop. Wait for the queued Requests to complete, process them,
    # and re-queue them again.

    sel = selectors.DefaultSelector()
    sel.register(cm.event_fd, selectors.EVENT_READ)

    while frames_done < TOTAL_FRAMES:
        # cm.get_ready_requests() does not block, so we use a Selector to wait
        # for a camera event. Here we should almost always get a single
        # Request, but in some cases there could be multiple or none.

        events = sel.select()
        if not events:
            continue

        reqs = cm.get_ready_requests()

        for req in reqs:
            frames_done += 1

            buffers = req.buffers

            # A ready Request could contain multiple buffers if multiple streams
            # were being used. Here we know we only have a single stream,
            # and we use next(iter()) to get the first and only buffer.

            assert len(buffers) == 1

            stream, fb = next(iter(buffers.items()))

            with libcamera.utils.MappedFrameBuffer(fb) as mfb:
                # Convert the raw buffer to opencv (numpy) buffer
                image = libcam_to_cv(mfb, stream.configuration)

                # Process the image
                image = cartoonify(image)

                # Show the image in a window
                cv2.imshow('Image', image)

                # This one is needed for the opencv to show the window...
                cv2.waitKey(1)

            meta = fb.metadata

            print("seq {:3}, bytes {}, frames queued/done {:3}/{:<3}"
                  .format(meta.sequence,
                          '/'.join([str(p.bytes_used) for p in meta.planes]),
                          frames_queued, frames_done))

            # If we want to capture more frames we need to queue more Requests.
            # We could create a totally new Request, but it is more efficient
            # to reuse the existing one that we just received.
            if frames_queued < TOTAL_FRAMES:
                req.reuse()
                cam.queue_request(req)
                frames_queued += 1

    # Stop the camera

    ret = cam.stop()
    assert ret == 0

    # Release the camera

    ret = cam.release()
    assert ret == 0

    return 0


if __name__ == '__main__':
    sys.exit(main())
