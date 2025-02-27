#!/usr/bin/env python3

from __future__ import annotations

import argparse
import kms
import libcamera as libcam
import selectors
import sys
import time

from collections import deque


class FPSCounter:
    def __init__(self, name=""):
        self.start_time = None
        self.frame_count = 0
        self.name = name

    def tick(self):
        if self.start_time is None:
            self.start_time = time.time()
            self.frame_count = 0

        self.frame_count += 1
        current_time = time.time()
        elapsed_time = current_time - self.start_time

        if elapsed_time >= 2:
            fps = self.frame_count / elapsed_time
            print(f"{self.name} FPS: {fps:.2f}")
            self.start_time = current_time
            self.frame_count = 0


class MyBuf:
    idx: int
    cam: libcam.Camera
    stream: libcam.Stream
    fb: kms.DmabufFramebuffer
    buffer: libcam.FrameBuffer


class KMSState:
    def __init__(self, mybufs: list[MyBuf], queue_buf):
        self.fps = FPSCounter("KMS")

        self.mybufs = mybufs
        self.queue_buf = queue_buf

        card = kms.Card()
        res = kms.ResourceManager(card)
        conn = res.reserve_connector()
        crtc = res.reserve_crtc(conn)
        mode = conn.get_default_mode()

        self.card = card
        self.crtc = crtc
        self.conn = conn
        self.mode = mode

        stream = mybufs[0].stream

        cfg = stream.configuration
        size = cfg.size
        w = size.width
        h = size.height
        fmt = kms.PixelFormats.find_drm_fourcc(cfg.pixel_format.fourcc)

        for mybuf in mybufs:
            buffer = mybuf.buffer
            plane = buffer.planes[0]  # assume single plane
            fd = plane.fd
            fb = kms.DmabufFramebuffer(card, w, h, fmt, [fd], [cfg.stride], [0])
            mybuf.fb = fb

        self.in_queue = deque()
        # Committed fb
        self.next_fb = None
        # On screen fb
        self.current_fb = None
        # Previous fb, will be unused on next pageflip
        self.prev_fb = None

    def setup(self, mybuf: MyBuf):
        # Do a modeset with the given buffer to get the display up
        fb = mybuf.fb
        kms.AtomicReq.set_mode(self.conn, self.crtc, fb, self.mode)
        self.current_fb = mybuf

    def queue_new_frame(self, mybuf: MyBuf):
        self.in_queue.append(mybuf)
        if not self.next_fb:
            self.handle_page_flip()

    def handle_page_flip(self):
        self.fps.tick()

        assert self.current_fb

        if self.prev_fb:
            self.queue_buf(self.prev_fb)
            self.prev_fb = None

        # Did we have something committed? If so, it's now current
        if self.next_fb:
            self.prev_fb = self.current_fb
            self.current_fb = self.next_fb
            self.next_fb = None

        if len(self.in_queue) > 0:
            self.next_fb = self.in_queue.popleft()

            ctx = kms.AtomicReq(self.card)
            ctx.add(self.crtc.primary_plane, "FB_ID", self.next_fb.fb.id)
            ctx.commit()

    def readdrm(self):
        for ev in self.card.read_events():
            if ev.type == kms.DrmEventType.FLIP_COMPLETE:
                self.handle_page_flip()


class CamState:
    def __init__(
        self, camera_id: int | str, format_str: str | None, size_str: str | None
    ):
        self.cam_fps = FPSCounter("Cam")

        self.cm = libcam.CameraManager.singleton()

        try:
            if camera_id.isnumeric():
                cam_idx = int(camera_id)
                cam = next(
                    (cam for i, cam in enumerate(self.cm.cameras) if i + 1 == cam_idx)
                )
            else:
                cam = next((cam for cam in self.cm.cameras if camera_id in cam.id))
        except Exception:
            print(f'Failed to find camera "{camera_id}"')
            return -1

        cam.acquire()

        cam_config = cam.generate_configuration([libcam.StreamRole.Viewfinder])

        stream_config = cam_config.at(0)

        if format_str:
            fmt = libcam.PixelFormat(format_str)
            stream_config.pixel_format = fmt

        if size_str:
            w, h = [int(v) for v in size_str.split("x")]
            stream_config.size = libcam.Size(w, h)

        cam_config.validate()

        cam.configure(cam_config)

        print(f"Camera configured to {stream_config}")

        self.cam = cam
        self.stream_config = stream_config
        self.stream = stream_config.stream

        self.is_first_req = True

    def add_req(self, mybuf: MyBuf):
        # Use the buffer index as the cookie
        req = self.cam.create_request(mybuf.idx)

        req.add_buffer(self.stream, mybuf.buffer)

        if self.is_first_req:
            # Looks like on rpi5 we get "interesting" fps if we don't set it explicitly
            req.set_control(libcam.controls.FrameDurationLimits, (33333, 33333))
            self.is_first_req = False

        self.cam.queue_request(req)

    def setup_hack(self, mybufs: list[MyBuf], kmsstate: KMSState):
        self.mybufs = mybufs
        self.kmsstate = kmsstate

    def handle_req(self):
        self.cam_fps.tick()

        reqs = self.cm.get_ready_requests()

        for req in reqs:
            buffers = req.buffers

            assert len(buffers) == 1

            idx = req.cookie
            mybuf = self.mybufs[idx]

            self.kmsstate.queue_new_frame(mybuf)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-c",
        "--camera",
        type=str,
        default="1",
        help="Camera index number (starting from 1) or part of the name",
    )
    parser.add_argument("-f", "--format", type=str, help="Pixel format")
    parser.add_argument("-s", "--size", type=str, help='Size ("WxH")')
    args = parser.parse_args()

    # Camera setup
    camstate = CamState(args.camera, args.format, args.size)

    # Allocate framebuffers

    stream = camstate.stream

    allocator = libcam.FrameBufferAllocator(camstate.cam)
    ret = allocator.allocate(stream)
    assert ret > 0

    num_bufs = len(allocator.buffers(stream))

    mybufs = []
    for i in range(num_bufs):
        mybuf = MyBuf()
        mybuf.idx = i
        mybuf.cam = camstate.cam
        mybuf.stream = stream
        mybuf.buffer = allocator.buffers(stream)[i]
        mybuf.fb = None
        mybufs.append(mybuf)

    kmsstate = KMSState(mybufs, camstate.add_req)
    # Give the first buffer to kms
    kmsstate.setup(mybufs[0])

    camstate.setup_hack(mybufs, kmsstate)

    # Start camera. Need to start it before we can queue buffers
    camstate.cam.start()

    # skip the first buf, as it has been given to kms
    for i in range(1, num_bufs):
        camstate.add_req(mybufs[i])

    def handle_key_event():
        sys.stdin.readline()
        print("Exiting...")
        return True

    sel = selectors.DefaultSelector()
    sel.register(camstate.cm.event_fd, selectors.EVENT_READ, camstate.handle_req)
    sel.register(kmsstate.card.fd, selectors.EVENT_READ, kmsstate.readdrm)
    sel.register(sys.stdin, selectors.EVENT_READ, handle_key_event)

    running = True

    while running:
        events = sel.select()
        for key, mask in events:
            # If the handler return True, we should exit
            if key.data():
                print("exit")
                running = False

    camstate.cam.stop()
    camstate.cam.release()

    return 0


if __name__ == "__main__":
    sys.exit(main())
