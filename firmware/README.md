# Firmware

MicroPython firmware for the ESP32-S3 boards. Master and slave share the `common` package.

| Folder | Content | Architecture |
|---|---|---|
| `common/` | ESP-NOW protocol, configuration schema (single source of all parameters), CRC, time base | [system architecture](../docs/system_architecture.md) section 7 |
| `slave/` | `hal/`, `measurement/`, `balancing/`, `link/`, `app/` | [slave architecture](../docs/slave_architecture.md) section 2 |
| `master/` | `hal/`, `core/`, `comm/` (incl. `comm/inverter/`), `app/` | [master architecture](../docs/master_architecture.md) section 2 |
| `build/` | custom MicroPython build (ESP32 CAN module, frozen modules) | W-02 |

On the device `common`, `slave` and `master` are top-level packages (frozen into the firmware), so the
code imports them the same way on the device and in the host tests (`import common.protocol`). The entry
points `slave/main.py` and `master/main.py` are called from the device's `main.py`, which is defined
together with the build (W-02).

## Rules

- **Hardware access only in `hal/`.** MicroPython-only modules (`machine`, `espnow`, `network`,
  `micropython`) are imported only there and in the entry points. Everything else is plain Python that also
  runs on CPython, so it can be tested on the host with simulated HAL objects (see [tests/](../tests/)).
- **MicroPython subset.** No `dataclasses`, `enum`, `typing` at run time, `abc`, or other CPython-only
  standard library modules; use `asyncio` (MicroPython flavour) for concurrency. Keep allocations in the
  100 ms protection loop small (garbage collection, plausibility check P1).
- **Safe state first.** Every entry point sets all outputs to their safe state before any other
  initialisation (SWS-001, MSW-002).
- **Traceability.** Reference the requirement IDs (e.g. `SAF-007`) in docstrings or comments where a
  requirement is implemented.
