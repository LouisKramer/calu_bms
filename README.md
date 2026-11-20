# calu_bms

Battery management system for a stationary high-voltage LFP home storage
(8 × 16S modules, expandable to 10, wireless slaves, master with CAN to the inverter).

This branch is a clean restart. Development follows the documents in [docs/](docs/):

1. [System requirements](docs/requirements.md) (draft, incl. configuration parameters)
2. [Slave requirements](docs/slave_requirements.md) (draft, hardware + software)
3. [Master requirements](docs/master_requirements.md) (draft, hardware + software), based on the
   [master concept review](docs/master_concept_review.md) of `hw/master/CALU_BMS_MASTER.epro2`
4. [Plausibility check](docs/plausibility_check.md) of the requirements
5. [System architecture](docs/system_architecture.md), [master architecture](docs/master_architecture.md), [slave architecture](docs/slave_architecture.md)
6. [Project plan](docs/plan.md) with work items ([tools/work_items.json](tools/work_items.json), GitHub issues via [tools/create_github_issues.py](tools/create_github_issues.py))

## Earlier work

The `playground` branch (formerly `main`) holds the first prototypes, firmware and hardware.
It is kept as a reference only, together with these branches:

| Branch | Content |
|---|---|
| `playground` | first master/slave firmware (MicroPython), EasyEDA hardware 1.2/1.3, tools, datasheets |
| `slave-hw-2.0.1.0` | firmware cleanup, drivers and bring-up for slave hardware 2.0.1.0 |
| `slave-hw-3.0.0.0` | flying-capacitor slave in KiCad/SKiDL, active balancer review |
