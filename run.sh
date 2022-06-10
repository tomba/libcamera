#!/bin/bash

#export LIBCAMERA_LOG_LEVELS=*:3
export LIBCAMERA_LOG_LEVELS=Python:DEBUG,*:ERROR
export PYTHONPATH=./build/src/py

python3 $*

