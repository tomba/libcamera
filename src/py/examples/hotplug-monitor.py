#!/usr/bin/env python3

# SPDX-License-Identifier: GPL-2.0-or-later
# Copyright (C) 2022, Tomi Valkeinen <tomi.valkeinen@ideasonboard.com>

# \todo Convert ctx and state dicts to proper classes, and move relevant
#       functions to those classes.

import libcamera as libcam
import sys


def main():
    cm = libcam.CameraManager.singleton()

    cm.camera_added = lambda c: print("Camera added:", c)
    cm.camera_removed = lambda c: print("Camera removed:", c)

    while True:
        try:
            cm.dispatch_events()
        except:
            break

    cm.discard_events()

    return 0


if __name__ == '__main__':
    sys.exit(main())
