# CALU BMS – Master Requirements (Hardware and Software)

| | |
|---|---|
| Status | Draft 0.1 |
| Parent | [System requirements](requirements.md) |
| Based on | master concept V1.4.1.0 (`hw/master/CALU_BMS_MASTER.epro2`), see [concept review](master_concept_review.md) |

Conventions as in the system requirements. **From** traces each requirement to the system requirements,
**Fn** to a finding of the concept review. Values marked **(P)** are new proposals.

---

## 1. Role of the master

The master
- disconnects the pack from the inverter (two-stage: SiC switches, then relays/contactors) and precharges,
- measures pack current, pack voltage, inverter voltage and insulation resistance,
- collects all slave data, runs the protection, SOC/SOH and balancing coordination,
- talks to the inverter (CAN, GCE protocol), Home Assistant (MQTT) and the user (web UI).

It is mounted at one module and supplied from it (any module of the stack).

## 2. Isolation domains

The board is split into domains; every barrier between them is rated for the full pack voltage
(**reinforced, ≥ 470 V working voltage**, SAF-013). This replaces the single ground of concept V1.4.1.0 (F1, F2).

| Domain | Reference | Contents |
|---|---|---|
| **LV** | negative of the supplying module | ESP32-S3, supply, LEDs, buzzer, USB, contactor drivers, logic |
| **HV−** | pack negative (BAT−) | shunt, isolated ADC (current, pack voltage, inverter voltage), BOT gate driver output side, insulation monitoring front end |
| **HV+** | TOP switch source node | TOP gate driver output side |
| **CAN** | inverter CAN ground | CAN transceiver bus side, ESD, termination, connector shield |
| **PE** | protective earth | insulation monitoring reference only |

```
              module supply ──► LV domain (ESP32) ──isolated SPI/GPIO──► HV− domain ─► shunt, U_BAT, U_INV, IMD
                                  │        │                                  └─ BOT gate driver
                                  │        └──isolated gate signal──────────────► HV+ domain ─► TOP gate driver
                                  └──isolated CAN──► CAN domain ─► inverter
```

---

## 3. Hardware requirements

### 3.1 Supply

| ID | Requirement | From |
|---|---|---|
| MHW-001 | The master shall be supplied from one module of the stack (4–16 cells): input range 10…60 V, components rated ≥ 100 V, reverse-polarity and transient protection. | HW-005, F9 |
| MHW-002 | The supply current shall be taken from the whole module (between its negative and positive end), never from a part of it. | MEA-006 |
| MHW-003 | Average power consumption **≤ 3 W (P)** without contactor coils; the contactor coil supply shall be separate (MHW-025). | HW-005, BAL-007 |
| MHW-004 | The master shall be operable from USB alone (no pack) for flashing and bench tests; the HV and contactor functions may be inactive then. | SYS-006 |

### 3.2 Stage 1 disconnect (SiC)

| ID | Requirement | From |
|---|---|---|
| MHW-020 | Each pole (HV+, HV−) shall have a bidirectional SiC switch (back-to-back MOSFETs) rated **≥ 1200 V** and for the configured continuous current within its temperature limits. Power path (switches, connectors, copper/bus bars) shall be rated for 100 A continuous; the cooling concept is decided in the plausibility check. | SAF-002, SAF-003, SYS-004, F6, F7 |
| MHW-021 | Each switch shall have a temperature sensor at the MOSFETs/heatsink; over-temperature (`t_switch_max`) shall open the switch. | SAF-008 |
| MHW-022 | Each pole shall have its own isolated gate driver and its own isolated gate supply; the gate-drive grounds of HV+ and HV− shall be isolated from each other and from the LV domain. | SAF-013, F1 |
| MHW-023 | The gate drivers shall be off when the MCU is in reset, unpowered or not driving the inputs (pull-downs, driver UVLO); turn-on shall additionally require a separate enable that is only set after the MCU's self test. | SAF-012, F11 |
| MHW-024 | A hardware over-current detection (fixed short-circuit threshold **250 A (P)**) shall switch off both SiC switches within **10 µs** without firmware involvement and latch the off state until the MCU resets the latch. | SAF-004, F3, F5 |

### 3.3 Stage 2 disconnect (relays/contactors) and precharge

| ID | Requirement | From |
|---|---|---|
| MHW-025 | The master shall drive at least **4** contactor/relay coils (HV+ main, HV− main, precharge, 1 spare), **12 V or 24 V (P)** coils up to **1 A (P)** each, from a separate coil supply input; all outputs shall be off on MCU reset, power loss or firmware crash. | SAF-002, SAF-012, F10 |
| MHW-026 | A precharge path (contactor + precharge resistor, external) shall be supported; the master measures the inverter-side voltage to verify precharge (SAF-006). | SAF-006, F8 |
| MHW-027 | Each main contactor shall have an auxiliary-contact feedback input (detects welded or not-closing contactors). | SAF-012, F8 |
| MHW-028 | The pack fuse is external; the master shall have an input to detect a blown fuse (voltage on both sides or fuse auxiliary contact). | SAF-005 |
| MHW-029 | The existing dry-contact outputs of the concept (2 relays) may be kept as general-purpose alarm outputs. | – |

### 3.4 Measurement (HV− domain)

| ID | Requirement | From |
|---|---|---|
| MHW-030 | All HV measurements shall be made in the HV− domain (pack negative) and transferred to the MCU over an isolated digital interface. | F2 |
| MHW-031 | Pack voltage (BAT+ − BAT−) and inverter voltage (INV+ − INV−, bipolar range, also with open switches) shall be measured with **±0.5 % (P)** of reading, range 0…**600 V (P)**. | MEA-005, SAF-006 |
| MHW-032 | Pack current shall be measured with a shunt in the HV− path: range **±150 A (P)** (`oc2_level`), accuracy ±0.5 %, offset < 50 mA, sampled at least **10 times per second (P)** and integrated without gaps for SOC. | MEA-004, EST-001, F3 |
| MHW-033 | Current and voltages shall be sampled simultaneously (same ADC conversion) for power and resistance calculations. | EST-004 |

### 3.5 Insulation monitoring

| ID | Requirement | From |
|---|---|---|
| MHW-040 | The master shall measure the insulation resistance of HV+ and HV− to protective earth (PE) in the range **10 kΩ…10 MΩ (P)**, with the pack connected or disconnected. | SAF-016, F8 |
| MHW-041 | The master shall have a PE terminal. The measurement shall inject only limited current (**≤ 1 mA (P)**) and be switchable off (to avoid interference with the inverter's own insulation check, OPEN-08). | SAF-016 |

### 3.6 Communication and user interface

| ID | Requirement | From |
|---|---|---|
| MHW-050 | CAN to the inverter through one isolated transceiver (reinforced isolation, e.g. ISOW1044 with integrated supply); ESD protection and connector shield referenced to the CAN domain only; 120 Ω termination switchable (jumper or MCU). | COM-001, F4 |
| MHW-051 | The CAN transceiver shall support silent (listen-only) operation for sniffing. | COM-007 |
| MHW-052 | The CAN connector shall be pin-compatible with the cable of the existing GCE BMS (RBMS07S70S50A) to the inverter. | COM-001 |
| MHW-053 | Wi-Fi/ESP-NOW antenna placement for ≥ 5 m range to all slaves through the battery rack. | COM-002 |
| MHW-054 | LEDs (status, error, contactor states), buzzer, reset and boot buttons, USB-C (flashing/console), UART test header. | – |
| MHW-055 | Real-time clock with backup (or NTP with fallback) for timestamps in logs. | SAF-014 |
| MHW-056 | Non-volatile storage for at least **30 days (P)** of 1-minute data and the complete fault log. | SAF-014, CFG-007 |

### 3.7 Insulation, environment, manufacturing

| ID | Requirement | From |
|---|---|---|
| MHW-060 | Clearance/creepage between all domains of section 2 and to the enclosure/mounting for ≥ 470 V working voltage, reinforced. | SAF-013 |
| MHW-061 | Operating ambient 0…40 °C, indoors, non-condensing. | HW-004 |
| MHW-062 | Manufacturable by JLCPCB; the power path (bus bars, heatsink) may be mechanical parts outside the PCB assembly. | HW-003 |

---

## 4. Software requirements

### 4.1 States and protection

| ID | Requirement | From |
|---|---|---|
| MSW-001 | States: INIT → STANDBY (pack disconnected) → PRECHARGE → CONNECTED → (DERATED) → FAULT (latched); plus SERVICE (configuration, calibration) and SNIFF (CAN listen-only, pack disconnected). | SAF-001, COM-007 |
| MSW-002 | At boot all outputs shall be in their safe state before any other initialisation; the HV enable (MHW-023) shall only be set after the self test. | SAF-012 |
| MSW-003 | The protection functions (SAF-007…SAF-010, SAF-016) shall run every **100 ms (P)** independently of communication with Home Assistant/web UI. | COM-006 |
| MSW-004 | Disconnect sequence: SiC off → wait until current ≈ 0 → contactors open → verify via feedback. Connect sequence: precharge contactor → wait for `precharge_dv` → main contactors → SiC on → precharge off. | SAF-002, SAF-006 |
| MSW-005 | A hardware watchdog shall reset the master if the firmware hangs for more than **1 s (P)**, which opens all switches (MHW-023, MHW-025). | SAF-012 |
| MSW-006 | Faults shall be latched and logged; critical faults require a user reset (web UI or Home Assistant, authenticated). | SAF-014 |

### 4.2 Slave management

| ID | Requirement | From |
|---|---|---|
| MSW-010 | The master shall discover the slaves, check that `modules_count` slaves with unique addresses are present, distribute the configuration and start operation only when all slaves confirmed it. | CFG-001, COM-003 |
| MSW-011 | The master shall provide the time base for synchronised measurement (MEA-008). | MEA-008 |
| MSW-012 | Slave timeouts per SAF-010. | SAF-010 |
| MSW-013 | The master shall compute the common balancing target and send balancing commands to all slaves, including the compensation of its own consumption on its supplying module. | BAL-005, BAL-007 |

### 4.3 Inverter communication

| ID | Requirement | From |
|---|---|---|
| MSW-020 | The master shall emulate the CAN protocol of the GCE BMS RBMS07S70S50A towards the GoodWe inverter, documented per COM-008. | COM-001, COM-008 |
| MSW-021 | SNIFF mode: log all CAN frames with timestamps (≥ 1 ms resolution) to file, downloadable via web UI. | COM-007 |
| MSW-022 | Replay/test mode: send recorded or synthetic sessions on a test bus to verify the implementation. | COM-008 |
| MSW-023 | No frames from the inverter for `inverter_timeout` → allowed currents zero, then disconnect. | COM-001 |

### 4.4 Estimation and limits

| ID | Requirement | From |
|---|---|---|
| MSW-030 | SOC by coulomb counting with rest and full-charge correction; SOH estimation; both stored non-volatile. | EST-001…003 |
| MSW-031 | Allowed charge/discharge current and voltage limits from cell voltages, temperatures, SOC taper and configuration, sent to the inverter at the cycle the inverter protocol requires. | EST-004 |

### 4.5 User interfaces and configuration

| ID | Requirement | From |
|---|---|---|
| MSW-040 | Home Assistant via MQTT with discovery: all values, states, faults; configuration parameters as writable entities (validated per CFG-003/CFG-004); fault reset. | COM-004, CFG-008 |
| MSW-041 | Web UI: status, cell overview, configuration, calibration, fault log, firmware update, CAN log download; password protected. | COM-005 |
| MSW-042 | OTA update of the master and (relayed) of all slaves with fallback on failure. | SYS-006 |
| MSW-043 | Data logging per MHW-056 and configuration change log per CFG-007. | CFG-007 |

---

## 5. Open points (master)

| ID | Question |
|---|---|
| MOPEN-01 | Power path and cooling for 100 A (see F6/F7, system OPEN-07). |
| MOPEN-02 | Contactor types and coil voltage (12 V or 24 V) and where the coil supply comes from. |
| MOPEN-03 | Confirm the values marked (P). |
