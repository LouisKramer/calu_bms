# calu_bms
BMS diy for ESP32 S3 WROOM N8R8
Micropython: https://docs.micropython.org/en/latest/index.html

This branch is a clean restart that currently only covers the slave hardware bring-up (HW 2.0.1.0).
The previous code (master, ADES1830 slave, SOC, protection, CAN, ...) is still available on `main`.

## Layout

    src/lib/      drivers (ADS1118, PCA9685, SN74HC154) and modules (cell_monitor, balancer)
    src/slave/    slave HW map (hw.py), boot.py, bring-up script, requirements.txt (upload mapping)
    tools/        upload.py, check.py
    hw/           EasyEDA slave project and datasheets

## Setup

    make tools      # pip install mpremote, esptool, mpy-cross

## Deploy and bring-up

    make fw PORT=COM5          # flash MicroPython (bin/), erases everything
    make all_slave PORT=COM5   # syntax check, wipe device (keeps /data), upload, reset
    make bringup PORT=COM5     # hardware checks (does not switch balancing)
    make help                  # all targets

The `requirements.txt` files map `<local path relative to the file> <device path>`.
Calibration data lives in `/data` on the device and survives `make clean`/`all_slave`, but not `make fw`.

If the device does not respond, put the ESP32-S3 into bootloader mode manually:

    1. Pull IO0 to low (jumper H1) and press the reset button
    2. Release after a second.

After start: boot.py is executed, then main.py (if present).
