# calu_bms
BMS diy for ESP32 S3 WROOM N8R8
Micropython: https://docs.micropython.org/en/latest/index.html
    - ESP32_GENERIC_S3-SPIRAM_OCT-20250911-v1.26.1 
    - https://micropython.org/download/ESP32_GENERIC_S3/

Transfer data to esp:
    1. pip install adafruit-ampy
    2. ampy --port COM4 get boot.py boot.py
    3. --port COM4 put boot.py

Put esp32 s3 into bootloader mode:  
    1. Pull Pin0 to low and press reset button
    2. Release the BOOT button after a second.

After start:
    1. boot.py is executed.
    2. main.py is executed.

