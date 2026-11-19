# CALU BMS – System Requirements

| | |
|---|---|
| Status | Draft 0.2 |
| Scope | Battery management system for a stationary high-voltage LFP home storage |
| Branches with earlier design work | `slave-hw-2.0.1.0` (firmware/drivers for slave 2.0.1.0), `slave-hw-3.0.0.0` (flying-capacitor slave, KiCad/SKiDL, active balancer review) |

Conventions:
- **shall** = mandatory, **should** = recommended, **may** = optional.
- Values marked **(P)** are proposals that still need confirmation.
- Every requirement has an ID so tests, design and firmware can refer to it.

---

## 1. System overview

```
                         CAN                    ESP-NOW (wireless)
  Inverter  <──────────────────────>  MASTER  <───────────────────>  SLAVE 1 … SLAVE 8
  (GoodWe GW8K-ET or larger)            │                              │ (one per 16S module)
                                        │ 2-stage disconnect           │ cell voltages, temperatures,
  HV+ ──── fuse ── SiC ── relay ────────┤ current, pack voltage        │ passive balancing,
  HV- ─────────────── SiC ── relay ─────┤ SOC/SOH, protection          │ optional active balancer
                                        │ Wi-Fi: web UI, Home Assistant
            8 modules × 16S LFP 350 Ah in series = 128S1P
```

| Item | Value |
|---|---|
| Cells | LFP, 350 Ah, 128 in series (8 modules × 16S), 1P |
| Nominal voltage / energy | 128 × 3.2 V ≈ 410 V, ≈ 143 kWh |
| Pack voltage range | 320 V (2.50 V/cell) … 467 V (3.65 V/cell) |
| Current (BMS rating) | 100 A charge, 100 A discharge, continuous (for future larger inverters) |
| Inverter | GoodWe GW8K-ET now, larger models later; CAN |

The full configuration (128S, 100 A) is the design target for a future larger inverter. With the
GW8K-ET the BMS runs with a smaller configuration (fewer modules and/or lower current limits) that fits
the inverter's battery voltage and current range.
| Installation | indoors, heated, not below 0 °C |

---

## 2. System requirements

| ID | Requirement |
|---|---|
| SYS-001 | The BMS shall monitor and protect a pack of 128 LFP cells in series, built from 8 modules of 16S. |
| SYS-002 | The BMS shall consist of one master and one slave per 16S module. |
| SYS-003 | The system shall be expandable by adding modules in series, up to the voltage limit of the connected inverter (see OPEN-01), and should support 4–16 cells per module. |
| SYS-004 | The BMS hardware shall be rated for 100 A continuous charge and discharge current (future larger inverters). The actual limits sent to the inverter shall be configurable and never exceed the cell, BMS or inverter ratings. |
| SYS-007 | The number of modules in series shall be configurable, so the same BMS can run a smaller pack within the GW8K-ET's battery range now and the full 128S pack with a larger inverter later. |
| SYS-005 | Parameters (cell limits, current limits, number of modules/cells, balancing thresholds) shall be configurable without changing firmware. |
| SYS-006 | Firmware of master and slaves shall be updatable without opening the modules (OTA). |

## 3. Safety and protection

| ID | Requirement |
|---|---|
| SAF-001 | The master shall disconnect the pack from the inverter (both poles) when any protection limit is exceeded. |
| SAF-002 | Disconnection shall be two-stage: **stage 1** SiC semiconductor switches open the current fast; **stage 2** relays/contactors then open galvanically at (near) zero current. Relays shall not be required to break load current. |
| SAF-003 | The stage-1 switches shall block current in both directions (charge and discharge). |
| SAF-004 | Short-circuit current shall be interrupted by stage 1 within **10 µs (P)**, independently of the firmware (hardware comparator). |
| SAF-005 | The pack shall have a DC fuse rated for the pack voltage as backup for a failed (shorted) stage-1 switch. |
| SAF-006 | Connecting the pack to the inverter shall use precharge of the inverter DC-link capacitance; the master shall verify the precharge (voltage difference **< 10 V (P)**) before closing. |
| SAF-007 | Cell limits (P): over-voltage **3.65 V**, under-voltage **2.50 V**; warning levels **3.55 V / 2.80 V** reduce the allowed current before cut-off. |
| SAF-008 | Temperature limits (P): charging **0…45 °C**, discharging **−10…55 °C**. Below 0 °C charging shall be blocked (no cell heating, indoor installation). |
| SAF-009 | Over-current limits (P): **110 A** for > 10 s and **150 A** for > 1 s lead to disconnection; short circuit per SAF-004. |
| SAF-010 | Loss of communication with any slave for more than **5 s (P)** shall be treated as a fault: currents reduced to zero, disconnection after **30 s (P)**. |
| SAF-011 | Every slave shall switch off all balancing when it receives no valid command from the master within **30 s (P)**, and during its own reset (hardware default off). |
| SAF-012 | The safe state (relays open, balancing off) shall also be reached on master power loss, reset or firmware crash (fail-safe hardware defaults, watchdog). |
| SAF-013 | All slave electronics float at their module potential (up to ~470 V to earth). Insulation between modules, slaves, enclosure and service interfaces shall be designed for the full pack voltage. Service USB on a module in the stack shall only be used through an isolator rated **≥ 1 kV (P)**. |
| SAF-014 | Faults shall be latched and logged; restart after a protection trip shall require the fault to be cleared, and for critical faults (over-voltage, short circuit) an explicit user reset. |

## 4. Measurement

| ID | Requirement |
|---|---|
| MEA-001 | Every cell voltage shall be measured with an accuracy of **±2 mV** over the operating temperature range, after calibration. |
| MEA-002 | All cells of the pack shall be measured at least every **1 s (P)**. |
| MEA-003 | Each slave shall measure **4 temperatures** per 16S module (cells/bus bars) plus its own board temperature. |
| MEA-004 | The master shall measure the pack current, both directions, with an accuracy of **±0.5 % (P)** and an offset error small enough for SOC (**< 50 mA (P)**). |
| MEA-005 | The master shall measure the pack voltage (battery side) and the inverter-side voltage (for precharge, SAF-006). |
| MEA-006 | The slave measurement shall not load the cells unevenly; the quiescent current of the slave shall be equal for all modules within **1 mA (P)**. |
| MEA-007 | Measurement shall detect open tap wires and implausible values (e.g. sum of cells vs. module voltage) and report them as faults. |
| MEA-008 | Cell voltages of all slaves shall be sampled time-synchronous within **100 ms (P)**, so that pack-level calculations use matching data. |

## 5. Balancing

| ID | Requirement |
|---|---|
| BAL-001 | Each slave shall provide passive balancing for each cell. |
| BAL-002 | Passive balancing current shall be **≥ 150 mA (P)** per cell; the bleed resistors shall stay within their rating at continuous operation of all channels. |
| BAL-003 | Each slave shall provide an interface for an optional active balancing module (enable + switching-clock signal), so active balancing can be added later without changing the slave. |
| BAL-004 | Balancing shall be paused during cell voltage measurement. |
| BAL-005 | The master shall coordinate balancing across all modules (common target voltage), so that modules are balanced to each other and not only internally. |
| BAL-006 | Balancing thresholds (start voltage, minimum difference) shall be configurable. |

## 6. State estimation

| ID | Requirement |
|---|---|
| EST-001 | The master shall estimate the state of charge (SOC) of the pack with an error of **< 5 % (P)**, using coulomb counting with correction at rest/full charge. |
| EST-002 | The master shall estimate the state of health (SOH, remaining capacity) of the pack. |
| EST-003 | SOC and SOH shall be stored non-volatile and survive a power loss. |
| EST-004 | The master shall calculate the allowed charge/discharge current and voltage limits continuously from cell voltages, temperatures and SOC and send them to the inverter. |

## 7. Communication and interfaces

| ID | Requirement |
|---|---|
| COM-001 | The master shall communicate with the inverter over CAN using the battery protocol the GoodWe inverter accepts. The protocol is not public and shall be reverse engineered from the traffic between an existing, working BMS and the inverter (see COM-007, OPEN-02). |
| COM-007 | The master hardware shall support a **listen-only CAN mode** (no ACK, no transmission) and log all frames with timestamps, so the existing BMS ↔ inverter traffic can be recorded without disturbing it. |
| COM-008 | The protocol implementation shall be documented (message IDs, cycle times, scaling, meaning, timeouts) and verified by replaying recorded sessions before it is used with the real inverter. |
| COM-009 | The BMS shall stay within the behaviour of the original BMS on the bus (cycle times, value ranges); unknown fields shall be sent with the values observed from the original BMS. |
| COM-002 | Master and slaves shall communicate wirelessly (ESP-NOW), which also provides galvanic isolation between modules. |
| COM-003 | Each slave shall have a hardware-configurable module address (position in the stack). |
| COM-004 | The master shall publish all measured values, states and faults to Home Assistant (MQTT). |
| COM-005 | The master shall provide a web interface over Wi-Fi for status, configuration and fault reset. |
| COM-006 | The safety function of the master shall not depend on Wi-Fi or Home Assistant being available. |

## 8. Hardware constraints

| ID | Requirement |
|---|---|
| HW-001 | Master and slaves shall use the ESP32-S3 (MicroPython firmware). |
| HW-002 | Slaves shall be supplied from their own module **or** from an isolated auxiliary supply (decision OPEN-04). |
| HW-003 | All boards shall be manufacturable by JLCPCB (PCB + assembly). |
| HW-004 | Operating ambient temperature: **0…40 °C (P)**, indoors, non-condensing. |

---

## 9. Open points

| ID | Question |
|---|---|
| OPEN-01 | GW8K-ET battery voltage and current range (datasheet) → defines the initial number of modules and current limits (SYS-007). |
| OPEN-02 | CAN protocol reverse engineering: which existing BMS/battery is it (brand, model), CAN bit rate, and the wiring/termination for tapping the bus. Capture plan: idle, charge, discharge, full, empty, BMS fault, BMS disconnected (inverter timeout behaviour). |
| OPEN-04 | Slave supply: from its own module or isolated auxiliary supply (affects cell load, number of cells per slave). |
| OPEN-05 | Insulation monitoring (pack vs. earth) was decided against. Check whether the inverter monitors the battery side; otherwise an insulation fault on a 410 V pack goes undetected. |
| OPEN-06 | Confirm all values marked **(P)**. |
