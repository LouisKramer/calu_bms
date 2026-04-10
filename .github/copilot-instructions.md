# Project Instructions

This repository targets embedded firmware running on MicroPython for the ESP32-S3-WROOM-1-N8R8.

## Target Definition

- Runtime: MicroPython
- MCU module: ESP32-S3-WROOM-1-N8R8
- Domain: battery management system firmware

## Development Guidance

- Keep code compatible with MicroPython on ESP32; do not assume full CPython support.
- Prefer lightweight implementations and avoid unnecessary allocations, background work, and large dependencies.
- Use hardware-facing modules and drivers already present in this repository before introducing new abstractions.
- Preserve behavior expected on constrained embedded hardware, including boot flow, peripheral access, and deterministic control logic.
- When proposing tests or utilities, distinguish clearly between host-side test code and code intended to run on the device.