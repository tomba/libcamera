#!/usr/bin/env python3

# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2022, Tomi Valkeinen <tomi.valkeinen@ideasonboard.com>

import libcamera as libcam
import selectors
import sys


def main():
    cm = libcam.CameraManager.singleton()

    sel = selectors.DefaultSelector()
    sel.register(cm.event_fd, selectors.EVENT_READ)

    print('Waiting for camera hotplug events... (CTRL-C to exit)')

    while True:
        try:
            events = sel.select()
            if not events:
                continue
        except KeyboardInterrupt:
            break

        events = cm.get_events()

        for ev in events:
            if ev.type == libcam.Event.Type.CameraAdded:
                print('Camera added:', ev.camera)
            elif ev.type == libcam.Event.Type.CameraRemoved:
                print('Camera removed:', ev.camera)

    return 0


if __name__ == '__main__':
    sys.exit(main())
