#!/bin/bash

PYTHONMALLOC=malloc PYTHONPATH=../../build/debug/py valgrind --suppressions=valgrind-pycamera.supp --leak-check=full --show-leak-kinds=definite --gen-suppressions=yes python3 test.py $*
