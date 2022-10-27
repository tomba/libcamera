#!/usr/bin/env python3

# SPDX-License-Identifier: BSD-3-Clause
# Copyright (C) 2022, Tomi Valkeinen <tomi.valkeinen@ideasonboard.com>
#
# The TensorFlow code adapted from picamera2 examples:
# Copyright (c) 2022 Raspberry Pi Ltd
# Author: Alasdair Allan <alasdair@raspberrypi.com>

# A simple capture example with opencv & TensorFlow. This is almost identical to
# simple-capture.py, except we use opencv & TensorFlow to process and show the
# image.

from pathlib import Path
import argparse
import cv2
import libcamera as libcam
import libcamera.utils
import numpy as np
import selectors
import sys
import tensorflow as tf

script_dir = Path(__file__).parent.absolute()

# Number of frames to capture
TOTAL_FRAMES = 10000


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


def InferenceTensorFlow(image, tf_data):
    labels = tf_data['labels']
    interpreter = tf_data['interpreter']

    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()
    height = input_details[0]['shape'][1]
    width = input_details[0]['shape'][2]
    floating_model = False
    if input_details[0]['dtype'] == np.float32:
        floating_model = True

    initial_h, initial_w, channels = image.shape

    picture = cv2.resize(image, (width, height))

    input_data = np.expand_dims(picture, axis=0)
    if floating_model:
        input_data = (np.float32(input_data) - 127.5) / 127.5

    interpreter.set_tensor(input_details[0]['index'], input_data)

    interpreter.invoke()

    detected_boxes = interpreter.get_tensor(output_details[0]['index'])
    detected_classes = interpreter.get_tensor(output_details[1]['index'])
    detected_scores = interpreter.get_tensor(output_details[2]['index'])
    num_boxes = interpreter.get_tensor(output_details[3]['index'])

    for i in range(int(num_boxes)):
        top, left, bottom, right = detected_boxes[0][i]
        classId = int(detected_classes[0][i])
        score = detected_scores[0][i]
        if score > 0.5:
            x1 = int(left * initial_w)
            y1 = int(top * initial_h)
            x2 = int(right * initial_w)
            y2 = int(bottom * initial_h)

            print(labels[classId], 'score = ', score)

            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0, 0))

            font = cv2.FONT_HERSHEY_SIMPLEX
            cv2.putText(image, labels[classId], (x1 + 10, y1 + 10), font, 1, (255, 255, 255), 2, cv2.LINE_AA)

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

    cv2.namedWindow("Image", cv2.WINDOW_AUTOSIZE)

    # Read and parse the labels to a dict

    with open(script_dir / "coco_labels.txt", 'r') as f:
        lines = f.readlines()

    kvps = [line.strip().split(maxsplit=1) for line in lines]
    kvps = [[int(kvp[0]), kvp[1]] for kvp in kvps]
    LABELS = dict(kvps)

    # Set up the interpreter

    interpreter = tf.lite.Interpreter(model_path=str(script_dir / "mobilenet_v2.tflite"))
    interpreter.allocate_tensors()

    tf_data = {
        'labels': LABELS,
        'interpreter': interpreter,
    }

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

                # Analyze and process the image
                image = InferenceTensorFlow(image, tf_data)

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
