# Firmware build

Placeholder for the custom MicroPython build (work item W-02, issue #3):

- MicroPython for ESP32-S3 with ESP-IDF ≥ 5.4: board variants N8R8 (slave) and N16R8 (master)
- ESP32 CAN (TWAI) support with listen-only mode: micropython/micropython#19461 or the user C module
  `micropython-esp32-twai` (MSW-024)
- `common/` and `slave/` or `master/` frozen into the firmware
- containerised build script (ESP-IDF image), later in GitHub Actions

Build output goes to `firmware/build/out/` (ignored by git).
