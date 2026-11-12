# calu_bms
BMS diy for ESP32 S3 WROOM N8R8
Micropython: https://docs.micropython.org/en/latest/index.html

## Layout

    src/common/   shared code (protocol, logger, master boot.py)
    src/lib/      drivers and modules
    src/master/   master application + requirements.txt (upload mapping)
    src/slave/    slave application (HW 2.0.1.0) + requirements.txt (upload mapping)
    tools/        upload.py, check.py, syslog server, resistor calculator
    hw/           EasyEDA projects and datasheets

## Setup

    make tools      # pip install mpremote, esptool, mpy-cross

`src/common/credentials.py` (WIFI_SSID, WIFI_PASS) is not versioned and must be created locally for the master.

## Deploy

    make fw PORT=COM5          # flash MicroPython (bin/), erases everything
    make all_slave PORT=COM5   # syntax check, wipe device (keeps /data), upload, reset
    make all_master PORT=COM5
    make run                   # run main.py in foreground with live output
    make help                  # all targets

The `requirements.txt` files map `<local path relative to the file> <device path>`.
Calibration data lives in `/data` on the device and survives `make clean`/`all_*`, but not `make fw`.

If the device does not respond, put the ESP32-S3 into bootloader mode manually:

    1. Pull IO0 to low (jumper H1) and press the reset button
    2. Release after a second.

After start: boot.py is executed, then main.py.
