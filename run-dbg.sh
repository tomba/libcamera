#!/bin/bash

export LIBCAMERA_LOG_LEVELS=*:3
export PYTHONPATH=./build/src/py

python3 -m pdb $*

