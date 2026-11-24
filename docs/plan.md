# CALU BMS – Project Plan

| | |
|---|---|
| Status | Draft 0.1 |
| Work items | [tools/work_items.json](../tools/work_items.json) (23 items, W-01…W-23) |
| GitHub | `python tools/create_github_issues.py --apply` creates labels, milestones and issues (needs the GitHub CLI `gh` and `gh auth login`; without `--apply` it only prints a dry run) |

---

## 1. Where to start: slave first, protocol test in parallel

**Recommendation: start with the slave hardware (M1), and run the cheap foundation and protocol work (M0) in
parallel on dev kits.**

| Reason | |
|---|---|
| Biggest technical risk first | ±2 mV cell measurement (MEA-001) is the core function of the BMS and can only be verified on real hardware. |
| Most mature design | The slave 3.0 design exists (KiCad/SKiDL, ERC clean); slave 4.0 is specified from it for drawing in EasyEDA (hw/slave/slave_4_0_schematic.md). |
| Low voltage, low risk | 60 V per board; can be tested on one module without the HV box. |
| Quantity | 10 boards needed; their lead time determines the integration date. |
| Master needs slaves | The master firmware can only be integrated with real slave data; host tests use simulated slaves meanwhile. |

The **inverter protocol test (W-05, W-06)** runs in parallel because it decides COM-001 and only needs an
ESP32-S3 dev kit and an isolated CAN transceiver breakout. If the BYD HVS/HVM emulation is accepted by the
GW8KN-ET, the reverse engineering of the GCE protocol is not needed.

The **master hardware (M2)** follows; its long-lead parts (contactors, fuse, gate drivers with thin LCSC
stock, PV15-27B12R3) are ordered early (W-13).

## 2. Milestones and order

```
M0 Foundation        W-01 skeleton ─┬─ W-03 config schema ─────────────────────────┐
                                    └─ W-04 ESP-NOW protocol ─────────────┐         │
                     W-02 MicroPython build ─┬─ W-05 CAN sniffer ─ W-06 protocol test (GW8KN-ET)
                                             │                            │         │
M1 Slave             W-07 schematic ─ W-08 PCB/order ──────┐              │         │
                     W-09 HAL ─ W-10 measurement ─┬─ W-12 bring-up, ±2 mV │         │
                                                  └─ W-11 link/states/balancing/low power
                                                                          │         │
M2 Master            W-13 HV box parts ─ W-14 schematic ─ W-15 PCB ─┐     │         │
                     W-16 HAL ──────────────────────────────────────┴─ W-20 bring-up ─ W-21 short-circuit test
                     W-17 core (protection, SOC, sequencer) ◄─────────────┴─────────┘
                     W-18 inverter protocol (after W-06, W-17) · W-19 HA/web/history/OTA
M3 Integration       W-22 master + 1 slave ─ W-23 commissioning with the full pack and the GW8KN-ET
```

| Milestone | Goal | Items |
|---|---|---|
| M0 Foundation | repository, build, shared libraries, protocol decision | W-01…W-06 |
| M1 Slave prototype | slave 4.0 verified on a real module | W-07…W-12 |
| M2 Master prototype | master 2.0 + HV box verified up to 600 V / 25 A on the bench | W-13…W-21 |
| M3 Integration | full system with the inverter | W-22, W-23 |

Suggested first sprint: W-01, W-02, W-07 (in parallel), then W-03/W-04 and W-05/W-06.

## 3. Working with GitHub

- Issues: one per work item, labels `area/*` and `type/*`, milestones M0…M3; dependencies are linked in
  the issue body ("Depends on #n").
- A GitHub Project (board view, columns Todo / In progress / Review / Done; roadmap view grouped by
  milestone) gives the overview; it has to be created once in the GitHub web UI and the issues added to it.
- Branches per work item (`w07-slave-schematic`), pull requests reference the issue (`Closes #n`); the
  requirement IDs in the issue body keep the traceability.
- Test reports go to `docs/test/`, so every "Done when" criterion has a document.

## 4. Open decisions that affect the plan

| Item | Affects |
|---|---|
| QA123C-1803R3 isolation rating confirmation by the vendor | W-14 |
| 1ED3860MC12M availability (6 pcs at LCSC) | W-13, W-14 |
| Protocol decision (BYD or GCE) | W-18 |
