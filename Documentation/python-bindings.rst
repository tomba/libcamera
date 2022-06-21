.. SPDX-License-Identifier: CC-BY-SA-4.0

.. _python-bindings:

Python Bindings for libcamera
=============================

.. warning::
    The bindings are under work, and the API will change.

Differences to the C++ API
--------------------------

As a rule of thumb the bindings try to follow the C++ API when possible. This
chapter lists the differences.

Mostly these differences fall under two categories:

1. Differences caused by the inherent differences between C++ and Python.
   These differences are usually caused by the use of threads or differences in
   C++ vs Python memory management.

2. Differences caused by the code being work-in-progress. It's not always
   trivial to create a binding in a satisfying way, and the current bindings
   contain simplified versions of the C++ API just to get forward. These
   differences are expected to eventually go away.

Coding Style
------------

The C++ code for the bindings follows the libcamera coding style as much as
possible. Note that the indentation does not quite follow the clang-format
style, as clang-format makes a mess of the style used.

The API visible to the Python side follows the Python style as much as possible.

This means that e.g. ``Camera::generateConfiguration`` maps to
``Camera.generate_configuration``.

CameraManager
-------------

The Python API provides a singleton CameraManager via ``CameraManager.singleton()``.
There is no need to start or stop the CameraManager.

Event Handling
--------------

The Python bindings do not expose the signals from the C++ side directly as the
signals are invoked from another thread and they may have real-time
constraints. Instead the bindings queue the received events internally and use
an eventfd to inform the user that there are events to be handled.

The user can wait on the eventfd (e.g. by using Python Selector), and use
``CameraManager.get_events()`` to reset the eventfd and get the events.

The CameraManager events (CameraAdded and CameraRemoved) are always enabled, but
of the Camera events only RequestCompleted is enabled by default. To enable
Disconnect or BufferCompleted event, use ``Camera.enable_camera_event()``.

The ``Camera.stop()`` method will return all events related to that Camera from
the event queue.

Controls & Properties
---------------------

The classes related to controls and properties are rather complex to implement
directly in the Python bindings. There are some simplifications in the Python
bindings:

- There is no ControlValue class. Python objects are automatically converted
  to ControlValues and vice versa.
- There is no ControlList class. A Python dict with ControlId keys and Python
  object values is used instead.
- There is no ControlInfoMap class. A Python dict with ControlId keys and
  ControlInfo values is used instead.
