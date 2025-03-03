#!/usr/bin/env python3

from __future__ import annotations

import os

os.environ['PYOPENGL_PLATFORM'] = 'egl'

import argparse
import libcamera as libcam
import selectors
import sys
from ctypes import cdll
import xcffib
import xcffib.xproto

from pixutils.fpscounter import FPSCounter

from cam_egl import EglState, EglSurface
from cam_gl_scene import GLScene
from cam_gl_types import MyBuf

class X11Window:
    def __init__(self, fullscreen: bool = False, num_frames: int | None = None):
        self.need_exit = False
        self.framenum = 0

        self.fullscreen = fullscreen
        self.num_frames = num_frames

        # Connect to X server using XCB
        self.conn = xcffib.Connection()
        self.xcb_setup = self.conn.get_setup()
        self.screen = self.xcb_setup.roots[0] # type: ignore
        self.xcb_fd =  self.conn.get_file_descriptor()

        # Set up window dimensions
        if self.fullscreen:
            self.width = self.screen.width_in_pixels
            self.height = self.screen.height_in_pixels
        else:
            self.width = 600
            self.height = 600

        # Create window
        self.window_id = self.conn.generate_id()

        mask = (
            xcffib.xproto.CW.OverrideRedirect |
            xcffib.xproto.CW.EventMask
        )

        values = [
            0,  # Override redirect
            xcffib.xproto.EventMask.Exposure |
            xcffib.xproto.EventMask.KeyPress |
            xcffib.xproto.EventMask.StructureNotify  # For resize events
        ]

        self.conn.core.CreateWindow(
            self.screen.root_depth,
            self.window_id,
            self.screen.root,
            0, 0,                     # x, y
            self.width, self.height,  # width, height
            0,                        # border width
            xcffib.xproto.WindowClass.InputOutput,
            self.screen.root_visual,
            mask,
            values
        )

        # Set up WM_DELETE_WINDOW protocol
        self.wm_protocols = self.conn.core.InternAtom(
            False, len('WM_PROTOCOLS'), 'WM_PROTOCOLS'
        ).reply().atom

        self.wm_delete_window = self.conn.core.InternAtom(
            False, len('WM_DELETE_WINDOW'), 'WM_DELETE_WINDOW'
        ).reply().atom

        self.conn.core.ChangeProperty(
            xcffib.xproto.PropMode.Replace,
            self.window_id,
            self.wm_protocols,
            xcffib.xproto.Atom.ATOM,
            32, 1,
            [self.wm_delete_window]
        )

        if self.fullscreen:
            self._set_fullscreen()

        self.conn.core.MapWindow(self.window_id)
        self.conn.flush()

        self.scene = GLScene()

    def _set_fullscreen(self):
        """Set the window to fullscreen using EWMH"""
        net_wm_state = '_NET_WM_STATE'
        net_wm_state_fullscreen = '_NET_WM_STATE_FULLSCREEN'

        cookie = self.conn.core.InternAtom(False, len(net_wm_state), net_wm_state)
        reply = cookie.reply()

        cookie2 = self.conn.core.InternAtom(False, len(net_wm_state_fullscreen),
                                          net_wm_state_fullscreen)
        reply2 = cookie2.reply()

        self.conn.core.ChangeProperty(
            xcffib.xproto.PropMode.Replace,
            self.window_id,
            reply.atom,
            xcffib.xproto.Atom.ATOM,
            32, 1,
            [reply2.atom]
        )

    def process_x11_events(self):
        event = self.conn.poll_for_event()
        while event:
            if isinstance(event, xcffib.xproto.ExposeEvent):
                pass  # Handle expose event if needed

            elif isinstance(event, xcffib.xproto.KeyPressEvent):
                if event.detail in (24, 9):  # Q or ESC key
                    print('Exit due to keypress')
                    self.need_exit = True

            elif isinstance(event, xcffib.xproto.ConfigureNotifyEvent):
                if (event.width != self.width or event.height != self.height):
                    self.width = event.width
                    self.height = event.height
                    self.scene.set_viewport(self.width, self.height)

            elif isinstance(event, xcffib.xproto.ClientMessageEvent):
                if event.data.data32[0] == self.wm_delete_window:
                    print('Exit due to window close')
                    self.need_exit = True

            event = self.conn.poll_for_event()

        if self.num_frames and self.framenum >= self.num_frames:
            self.need_exit = True

        return self.need_exit

    def handle_key_event(self):
        sys.stdin.readline()
        print('Exiting...')
        self.need_exit = True

    def setup(self, egl_surface: EglSurface, mybufs: list[MyBuf], add_req):
        self.egl_surface = egl_surface
        self.add_req = add_req

        self.scene.setup(egl_surface, mybufs)
        self.scene.set_viewport(self.width, self.height)

        egl_surface.make_current()
        egl_surface.swap_buffers()

    def queue_new_frame(self, mybuf: MyBuf):
        self.scene.render(mybuf)
        self.egl_surface.swap_buffers()

        self.add_req(mybuf)

    def cleanup(self):
        """Clean up XCB resources"""
        self.conn.core.UnmapWindow(self.window_id)
        self.conn.core.DestroyWindow(self.window_id)
        self.conn.flush()
        self.conn.disconnect()



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

    def setup_hack(self, mybufs: list[MyBuf], xwindow: X11Window):
        self.mybufs = mybufs
        self.xwindow = xwindow

    def handle_req(self):
        self.cam_fps.tick()

        reqs = self.cm.get_ready_requests()

        for req in reqs:
            buffers = req.buffers

            assert len(buffers) == 1

            idx = req.cookie
            mybuf = self.mybufs[idx]

            self.xwindow.queue_new_frame(mybuf)


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
        mybuf.fd = mybuf.buffer.planes[0].fd
        mybufs.append(mybuf)

    window = X11Window()

    # Get X11 Display for EGL initialization
    x11 = cdll.LoadLibrary('libX11.so.6')
    native_display = x11.XOpenDisplay(None)
    egl_state = EglState(native_display)
    egl_surface = EglSurface(egl_state, window.window_id)

    window.setup(egl_surface, mybufs, camstate.add_req)

    camstate.setup_hack(mybufs, window)

    # Start camera. Need to start it before we can queue buffers
    camstate.cam.start()

    # skip the first buf, as it has been given to kms
    for i in range(num_bufs):
        camstate.add_req(mybufs[i])

    def handle_key_event():
        sys.stdin.readline()
        print("Exiting...")
        return True

    sel = selectors.DefaultSelector()
    sel.register(camstate.cm.event_fd, selectors.EVENT_READ, camstate.handle_req)
    sel.register(window.xcb_fd, selectors.EVENT_READ, window.process_x11_events)
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
