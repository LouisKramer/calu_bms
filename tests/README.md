# Host tests

Tests run on the PC with CPython and pytest; the firmware packages are importable as on the device
(`pythonpath = ["firmware"]` in [pyproject.toml](../pyproject.toml)).

```
pip install -r requirements-dev.txt
pytest
```

Layout mirrors the firmware: `tests/common/`, `tests/slave/`, `tests/master/`. Hardware is replaced by
simulated HAL objects; slaves, current and inverter are simulated for the master tests
(see [firmware/README.md](../firmware/README.md)). Test reports of hardware tests go to `docs/test/`.
