# calu_bms

Battery management system for a stationary high-voltage LFP home storage
(8 × 16S modules, wireless slaves, master with CAN to the inverter).

This branch is a clean restart. Development follows the documents in [docs/](docs/):

1. [Requirements](docs/requirements.md) (draft)
2. Architecture (next)

## Earlier work

The `main` branch is the playground where the first prototypes, firmware and hardware were built.
It is kept as a reference only, together with these branches:

| Branch | Content |
|---|---|
| `main` | first master/slave firmware (MicroPython), EasyEDA hardware 1.2/1.3, tools, datasheets |
| `slave-hw-2.0.1.0` | firmware cleanup, drivers and bring-up for slave hardware 2.0.1.0 |
| `slave-hw-3.0.0.0` | flying-capacitor slave in KiCad/SKiDL, active balancer review |
