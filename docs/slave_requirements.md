# CALU BMS – Slave Requirements (Hardware and Software)

| | |
|---|---|
| Status | Draft 0.4 |
| Parent | [System requirements](requirements.md) |

Conventions as in the system requirements. **From** traces each requirement to its system requirement.

---

## 1. Role of the slave

One slave per battery module (4–16 LFP cells in series). The slave
- measures all cell voltages, the module temperatures and its board temperature,
- performs passive balancing and controls an optional active balancer,
- sends its data to the master and executes the master's commands (balancing, configuration),
- protects its own module locally (balancing off, fault report), but never switches the pack current.

```
            module (4..16 cells)                         master
  T0 … T16 ──► cell measurement ─┐                         ▲
  4 × temp ──► temperature ──────┼─► ESP32-S3 ─ ESP-NOW ───┘
               passive balancing ◄┤      │
  active balancer ◄─ EN + clock ──┘      └─ address DIP, LEDs, USB (service)
```

---

## 2. Hardware requirements

### 2.1 Cell connection and measurement

| ID | Requirement | From |
|---|---|---|
| SHW-001 | The slave shall connect to 4–16 cells in series through one cell tap connector with 17 taps (T0 = module negative … T16). Unused taps are bridged to the top tap of the module. | SYS-003 |
| SHW-002 | Every cell voltage shall be measured with an accuracy of **±2 mV** over 0…40 °C board temperature, after a per-board calibration. | MEA-001 |
| SHW-003 | The cell voltage measurement range shall be at least **0…4.5 V** per cell, so over-voltage beyond the LFP limit is still measured and not clipped. Negative cell voltages (reversed or open tap) shall be detected. | SAF-007, MEA-007 |
| SHW-004 | The resolution of the cell voltage measurement shall be **≤ 0.5 mV**. | MEA-001 |
| SHW-005 | A complete measurement of all cells of the module shall take **≤ 0.5 s**, so the shortest `meas_period` (0.5 s) can be met. | MEA-002 |
| SHW-006 | The hardware shall allow detecting an open tap wire on every tap. | MEA-007 |
| SHW-007 | The slave shall measure the total module voltage independently of the cell measurement (plausibility check, `plaus_tol`). | MEA-007 |
| SHW-008 | Each tap shall be protected by a fuse or current-limiting element on the board, so a board fault cannot short a cell through the harness. | SAF-012 |
| SHW-009 | The current drawn from the cells for measurement shall be equal for all cells of the module, and the total current from the module shall not depend on the measurement state. | MEA-006 |

### 2.2 Temperature

| ID | Requirement | From |
|---|---|---|
| SHW-010 | The slave shall provide **4** connectors for external temperature sensors on the cells/bus bars, accuracy **±1 °C**, range **−20…85 °C**. | MEA-003 |
| SHW-011 | The slave shall measure its board temperature at the balancing resistors and at the measurement circuit. | MEA-003, SAF-008 |
| SHW-012 | A missing or faulty temperature sensor shall be detectable. | MEA-007 |

### 2.3 Balancing

| ID | Requirement | From |
|---|---|---|
| SHW-020 | The slave shall provide one passive balancing channel per cell, **≥ 150 mA** at 3.2 V cell voltage. | BAL-001, BAL-002 |
| SHW-021 | All 16 balancing channels shall be able to run continuously at the same time with every component within its rating at 40 °C ambient, without heatsink or fan. | BAL-002, HW-004 |
| SHW-022 | All balancing channels shall be off in hardware when the MCU is in reset, unpowered or not driving the outputs. | SAF-011, SAF-012 |
| SHW-023 | Balancing shall be switchable off for all channels at once within **1 ms** (measurement windows). | BAL-004 |
| SHW-024 | The balancing current shall not flow through the measurement path (separate traces or compensated), so balancing of one cell does not falsify neighbouring cells after the pause. | BAL-004, MEA-001 |

### 2.4 Active balancer interface

| ID | Requirement | From |
|---|---|---|
| SHW-030 | The slave shall provide a connector for an external active balancer with: GND (module negative), +3.3 V supply (**≤ 50 mA**), enable, switching clock. | BAL-003 |
| SHW-031 | The clock output shall be programmable from **100 Hz to 5 kHz**, 50 % duty, 3.3 V logic. | BAL-003 |
| SHW-032 | Enable and clock shall default to off (low) when the MCU is in reset or unpowered. | SAF-011, SAF-012 |
| SHW-033 | The active balancer's power current shall never flow through the slave or its cell tap connector; the balancer connects to the cells with its own harness. | BAL-003 |

### 2.5 Supply

| ID | Requirement | From |
|---|---|---|
| SHW-040 | The slave shall be supplied from its own module (whole module voltage between T0 and the top tap). | HW-002, MEA-006 |
| SHW-041 | Supply input range **10…60 V** (4…16 cells, 2.5…3.65 V), components rated ≥ 100 V, reverse-polarity and transient protection; the supply current shall come from the whole module, never from a part of it. | HW-002, MEA-006 |
| SHW-043 | Average power consumption **≤ 2 W** (radio transmission over Wi-Fi/ESP-NOW included); the consumption shall be the same for all slaves within **1 mA** (same firmware, same duty cycle, radio power saving off), so no module is discharged more than another. | MEA-006 |
| SHW-045 | In the low-power state (SAF-017) the slave shall draw **≤ 1 mA (P)** average from its module: supply converter with low quiescent current, ESP32-S3 deep sleep, measurement circuit and reference switched off. | SAF-017 |
| SHW-044 | The slave shall be operable from USB alone (no cells) for flashing and bench tests. | SYS-006 |

### 2.6 MCU, communication, addressing, indicators

| ID | Requirement | From |
|---|---|---|
| SHW-050 | MCU: ESP32-S3 module with PSRAM, running MicroPython. | HW-001 |
| SHW-051 | The radio range shall cover the battery installation (**≥ 5 m** through the battery rack); the antenna shall be placed so it is not shielded by the module enclosure. The layout shall also allow the ESP32-S3-WROOM-1**U** variant with external antenna **(P)**. | COM-002 |
| SHW-052 | A 4-bit hardware address switch (0…15) shall set the module position in the stack. | COM-003 |
| SHW-053 | Two LEDs (status, error) shall show the operating state locally. | – |
| SHW-054 | A USB-C connector shall provide flashing and a serial console; a reset and a boot button shall be present. | SYS-006 |

### 2.7 Insulation, environment, manufacturing

| ID | Requirement | From |
|---|---|---|
| SHW-060 | Inside the board: clearance and creepage for the module voltage (≤ 60 V). Between the board and its mounting/enclosure/earth and the USB service port: reinforced, ≥ 600 V working voltage (SAF-013). | SAF-013 |
| SHW-061 | Mounting holes and board edge shall keep the insulation distances of SHW-060 (no copper near mounting holes). | SAF-013 |
| SHW-062 | Operating ambient 0…40 °C, indoors, non-condensing. | HW-004 |
| SHW-063 | The board shall be manufacturable and assembled by JLCPCB; parts from the JLCPCB/LCSC library where possible. | HW-003 |
| SHW-064 | Each board shall have test points for supply rails and key measurement signals, so the calibration and production test can be done without probing component pins. | SWS-070 |

---

## 3. Software requirements

### 3.1 Start-up and states

| ID | Requirement | From |
|---|---|---|
| SWS-001 | At boot the slave shall set all outputs to their safe state (balancing off, active balancer off) before any other initialisation. | SAF-012 |
| SWS-002 | After boot the slave shall run a self test (measurement circuit present, balancing driver present, number of temperature sensors, supply voltage, calibration data valid) and report the result to the master. | MEA-007 |
| SWS-003 | The slave shall implement the states INIT → SEARCH (looking for the master) → CONFIG (waiting for configuration) → RUN, plus FAULT. Balancing is only allowed in RUN. | SAF-011, CFG-001 |
| SWS-004 | A hardware watchdog shall reset the slave if the firmware hangs for more than **2 s**. | SAF-012 |
| SWS-005 | Low-power state per SAF-017 (on command of the master or by itself after `slave_timeout_trip` without master while a cell is below `cell_uv_warn`): balancing off, deep sleep, wake-up every **10 min (P)**, measure, report, sleep again. | SAF-017 |

### 3.2 Measurement

| ID | Requirement | From |
|---|---|---|
| SWS-010 | The slave shall measure all configured cells every `meas_period`, start-time synchronised to the master's time base within **100 ms** across all slaves. | MEA-002, MEA-008 |
| SWS-011 | Balancing (passive and active) shall be paused during each cell measurement, including a settling time before sampling. | BAL-004 |
| SWS-012 | The slave shall apply its calibration data and report calibrated cell voltages, module voltage, temperatures and board temperatures with a timestamp. | MEA-001 |
| SWS-013 | The slave shall detect and report: open tap wire, cell voltage out of measurement range, module voltage vs. cell sum outside `plaus_tol`, missing/faulty temperature sensor, measurement circuit not responding. | MEA-007 |
| SWS-014 | Only `cells_per_module` cells shall be evaluated; unused (bridged) taps shall be checked to be at the top tap's voltage. | SYS-003 |

### 3.3 Communication with the master

| ID | Requirement | From |
|---|---|---|
| SWS-020 | Communication with the master shall use ESP-NOW with encryption (pairing key set at commissioning). The firmware shall support at least 10 encrypted peers (ESP-IDF default is 7) or authenticate messages in the application **(P)**. | COM-002 |
| SWS-021 | Every message shall contain the module address, a message type, a sequence number and a protocol version; corrupted, duplicated, out-of-order or foreign messages shall be discarded. | COM-002, COM-003 |
| SWS-022 | The slave shall send its measurement data after every measurement cycle. | MEA-002 |
| SWS-023 | Limit violations detected by the slave (`cell_ov_warn`/`cell_uv_warn` and the trip levels, temperature limits) shall be sent immediately as an event message, within **200 ms** of the measurement. | SAF-007, SAF-008 |
| SWS-024 | The slave shall synchronise its time base to the master periodically and report the remaining offset. | MEA-008 |
| SWS-025 | The protocol shall be versioned; a slave with an incompatible protocol version shall refuse to enter RUN and report the version mismatch. | SYS-006 |

### 3.4 Balancing control

| ID | Requirement | From |
|---|---|---|
| SWS-030 | The slave shall balance the cells selected by the master (target voltage per BAL-005) or, if instructed, select the cells itself from `bal_start_v` and `bal_delta` relative to the master's target. | BAL-005, BAL-006 |
| SWS-031 | Balancing shall stop when no valid balancing command arrives within `slave_bal_timeout`. | SAF-011 |
| SWS-032 | Balancing of a cell shall stop locally, without waiting for the master, when the cell is below `cell_uv_warn` or a board temperature exceeds `t_board_max`. | SAF-007, SAF-008 |
| SWS-033 | The active balancer shall be controlled with `bal_active_en` and `bal_active_freq`; it shall be stopped during measurement, on any fault and on communication loss. | BAL-003, BAL-004 |
| SWS-034 | The slave shall report the balancing state (active cells, duty/time) to the master. | BAL-005 |

### 3.5 Configuration, calibration, update

| ID | Requirement | From |
|---|---|---|
| SWS-040 | The slave shall receive its configuration from the master, validate it (ranges, version, checksum), store it non-volatile and confirm it. Invalid configuration shall be rejected and reported. | CFG-001, CFG-002, CFG-003 |
| SWS-041 | The module address shall come only from the hardware address switch, not from the configuration. | COM-003 |
| SWS-042 | Calibration data shall be stored on the slave separately from the configuration and shall survive configuration resets and firmware updates. A calibration procedure against reference cell voltages shall be available. | CFG-009, MEA-001 |
| SWS-043 | Firmware updates shall be possible over the air, started from the master; a failed update shall fall back to the previous firmware. | SYS-006 |

### 3.6 Diagnostics and logging

| ID | Requirement | From |
|---|---|---|
| SWS-050 | The slave shall keep a fault log of the last **100** events (time, type, values) in non-volatile memory and transfer it to the master on request. | SAF-014 |
| SWS-051 | The LEDs shall show the state: RUN, SEARCH/CONFIG, balancing active, FAULT (distinct blink patterns). | SHW-053 |
| SWS-052 | A service console over USB shall show live values, state and log, and allow running the calibration and hardware self test. | SHW-054 |

### 3.7 Production test

| ID | Requirement | From |
|---|---|---|
| SWS-070 | A production/bring-up test script shall check all hardware functions (measurement channels, balancing channels one at a time, temperature inputs, address switch, LEDs, active balancer outputs) and print a pass/fail report. | HW-003 |

---

## 4. Open points (slave)

None at the moment (supply concept decided: own module; all proposed values confirmed).
