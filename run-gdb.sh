#!/bin/bash

export LIBCAMERA_LOG_LEVELS=*:3
export PYTHONPATH=./build/src/py

gdb --args python3 $*

