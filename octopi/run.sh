#!/bin/sh

export DISPLAY=:0
cd /home/pi/qtpi
python3 /home/pi/qtpi/test.py 2> /home/pi/qtpi/error.log
