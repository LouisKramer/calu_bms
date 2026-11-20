# CALU BMS – Master Requirements (Hardware and Software)

| | |
|---|---|
| Status | Draft 0.5 |
| Parent | [System requirements](requirements.md) |
| Based on | master concept V1.4.1.0 (`hw/master/CALU_BMS_MASTER.epro2`), see [concept review](master_concept_review.md) |

Conventions as in the system requirements. **From** traces each requirement to the system requirements,
**Fn** to a finding of the concept review. Values marked **(P)** are new proposals (all earlier values are confirmed).

---

## 1. Role of the master

The master
- disconnects the pack from the inverter (two-stage: SiC switches, then relays/contactors) and precharges,
- measures pack current, pack voltage, inverter voltage and insulation resistance,
- collects all slave data, runs the protection, SOC/SOH and balancing coordination,
- talks to the inverter (CAN, GCE protocol), Home Assistant (MQTT) and the user (web UI).

It can be mounted at any position of the stack; it is supplied from the whole pack through an isolated HV DC/DC.

## 2. Isolation domains

The board is split into domains. Barriers between an HV domain (HV−, HV+) and the LV, CAN or PE side are
**reinforced, ≥ 600 V working voltage**; the barrier between HV− and HV+ is at least basic for 600 V
(SAF-013, MHW-060). This replaces the single ground of concept V1.4.1.0 (F1, F2).

| Domain | Reference | Contents |
|---|---|---|
| **LV** | secondary of the isolated HV DC/DC (floating, not connected to any module) | ESP32-S3, low-voltage supplies, 12 V coil supply and contactor drivers, LEDs, buzzer, USB, logic |
| **HV−** | pack negative (BAT−) | HV DC/DC primary side (input BAT+ − BAT−), Hall current sensor, ADC (current, pack voltage, inverter voltage), BOT gate driver output side, insulation monitoring front end |
| **HV+** | TOP switch source node | TOP gate driver output side |
| **CAN** | inverter CAN ground | CAN transceiver bus side, ESD, termination, connector shield |
| **PE** | protective earth | insulation monitoring reference only |

```
  pack (BAT+/BAT−, behind fuse) ──► HV DC/DC ══isolated══► LV domain (ESP32, 12 V coils)
                                  LV domain ──isolated SPI/GPIO──► HV− domain ─► I (Hall), U_BAT, U_INV, IMD
                                  │        │                                  └─ BOT gate driver
                                  │        └──isolated gate signal──────────────► HV+ domain ─► TOP gate driver
                                  └──isolated CAN──► CAN domain ─► inverter
```

---

## 3. Hardware requirements

### 3.1 Supply

| ID | Requirement | From |
|---|---|---|
| MHW-001 | The master shall be supplied from the whole pack (BAT+ − BAT−, battery side of the disconnect, behind the pack fuse) through an isolated DC/DC converter: input range **150…600 V** (from the smallest pack allowed by the CFG-003 cross-check at `cell_uv_trip` up to 10 modules at 3.65 V/cell = 584 V), reinforced isolation ≥ 600 V working voltage, own input fuse (2 A / 1000 V DC), inrush limiting. Selected: **Mornsun PV15-27B12R3** (100…1000 V DC in, 12 V / 15 W, reinforced, 4000 VAC). | HW-005, SAF-013, F9 |
| MHW-002 | No supply current shall be taken from a part of the stack (single module or cell group); the master loads all cells equally. | HW-005, MEA-006 |
| MHW-003 | Average power consumption **≤ 3 W** without contactor coils; the coil power is limited separately (MHW-025). The DC/DC shall deliver at least **15 W** continuous (master + holding of all contactors ≈ 7 W); the pull-in of one contactor at a time (≈ 12 W for ≈ 0.1 s, contactors closed one after another, MSW-004) is taken from a buffer capacitor on the 12 V rail. | HW-005 |
| MHW-004 | The master shall be operable from USB alone (no pack) for flashing and bench tests; the HV and contactor functions may be inactive then. Because the LV domain is separated from all HV domains by reinforced isolation (incl. the coil-to-contact isolation of the contactors), the master USB port does not need the extra isolator of SAF-013. | SYS-006, SAF-013 |

### 3.2 Stage 1 disconnect (SiC)

| ID | Requirement | From |
|---|---|---|
| MHW-020 | Each pole (HV+, HV−) shall have a bidirectional SiC switch of two back-to-back **ST SCT020H120G3AG** (1200 V, 18.5 mΩ typ at 25 °C / 37 mΩ at 175 °C, H²PAK-7, same footprint as the SCT040H120G3AG of the concept), rated for **25 A continuous** (plus `oc1_level`/`oc2_level` for their times) within its temperature limits. The MOSFETs shall be mounted on heatsinks sized for the conduction loss at 25 A (≤ 46 W per pole at T<sub>j</sub> = 175 °C, see plausibility check). Connectors and copper of the power path shall be rated for 25 A continuous. | SAF-002, SAF-003, SYS-004, F6, F7 |
| MHW-021 | Each switch shall have a temperature sensor at the MOSFETs/heatsink; over-temperature (`t_switch_max`) shall open the switch. | SAF-008 |
| MHW-022 | Each pole shall have its own isolated gate driver and its own isolated gate supply; the gate-drive grounds of HV+ and HV− shall be isolated from each other and from the LV domain. Gate driver **Infineon EiceDRIVER X3 Digital 1ED3860MC12M (P)** (reinforced per IEC 60747-17, VIOWM 1250 Vrms / 1767 VDC, creepage > 8 mm, 6 A, DESAT with soft turn-off, I²C configuration; one driver per pole drives both gates). Gate supply **Mornsun QA123C-1803R3** (12 V in from the coil rail, **+18 V / −3 V**, reinforced; creepage/working voltage ≥ 600 V DC to be confirmed by the vendor), fallback TI UCC14141-Q1 set to +18 V / −4 V. The gate voltages shall be inside the **recommended** range of the MOSFET (SCT020H120G3AG: −5…+18 V). | SAF-013, F1, F12, F13 |
| MHW-023 | The gate drivers shall be off when the MCU is in reset, unpowered or not driving the inputs (pull-downs, driver UVLO); turn-on shall additionally require a separate enable that is only set after the MCU's self test. | SAF-012, F11 |
| MHW-024 | A hardware over-current detection (fixed short-circuit threshold **50 A**, FAULT output of the current sensor) shall switch off both SiC switches within **10 µs** without firmware involvement and latch the off state until the MCU clears it: the sensor FAULT is passed through an isolator channel to the wired-AND fault pins (FLT_N) of both gate drivers, which forces their soft turn-off and latches the fault in the drivers. | SAF-004, F3, F5 |

### 3.3 Stage 2 disconnect (relays/contactors) and precharge

| ID | Requirement | From |
|---|---|---|
| MHW-025 | The master shall drive at least **4** contactor/relay coils (HV+ main, HV− main, precharge, 1 spare) with **12 V** coils up to **1 A** pull-in current each. The 12 V coil supply shall be generated on the master from the HV DC/DC (MHW-001). The drivers shall reduce the coil current to holding level after pull-in (PWM economizer, or contactors with built-in economizer), so that the holding power of all closed contactors together is **≤ 4 W**. All outputs shall be off on MCU reset, power loss or firmware crash. Main contactors: rated **≥ 750 V DC and ≥ 40 A continuous (P)**, able to break `oc2_level` at 600 V DC in **both** current directions as an emergency (failed-short SiC switch) **(P)**. | SAF-002, SAF-012, F10 |
| MHW-026 | A precharge path (contactor + precharge resistor, external) shall be supported; the master measures the inverter-side voltage to verify precharge (SAF-006). The precharge resistor shall be pulse-rated for **≥ 200 J** (½ C V² of the inverter DC link) and thermally protected (PTC precharge resistor or thermal fuse). | SAF-006, F8 |
| MHW-027 | Each main contactor shall have an auxiliary-contact feedback input (detects welded or not-closing contactors). | SAF-012, F8 |
| MHW-028 | The pack fuse is external: **1000 V DC**, DC breaking capacity **≥ 20 kA**, **32…40 A**, battery/semiconductor characteristic (e.g. 14 × 51 mm or NH00 gBat/aR). The master shall have an input to detect a blown fuse (voltage on both sides or fuse auxiliary contact). | SAF-005 |
| MHW-029 | The existing dry-contact outputs of the concept (2 relays) may be kept as general-purpose alarm outputs. | – |

### 3.4 Measurement (HV− domain)

| ID | Requirement | From |
|---|---|---|
| MHW-030 | All HV measurements shall be made in the HV− domain (pack negative) and transferred to the MCU over an isolated digital interface. | F2 |
| MHW-031 | Pack voltage (BAT+ − BAT−) and inverter voltage (INV+ − INV−, bipolar range, also with open switches) shall be measured with **±0.5 %** of reading, range 0…**600 V**. | MEA-005, SAF-006 |
| MHW-032 | Pack current shall be measured with a Hall current sensor **ACS71240LLCBTR-050B3** (SOIC-8, ±50 A, 26.4 mV/A, FAULT at ±50 A; same footprint as the 030B3 of the concept) in the HV− path, supplied and read in the HV− domain (the sensor then needs only functional isolation; its 297 Vrms basic isolation would not be enough towards the LV domain). Accuracy **±1 %** of reading after calibration, offset **≤ 150 mA** after automatic zeroing at zero current (pack disconnected), sampled at least **10 times per second** and integrated without gaps for SOC. Its FAULT output provides the hardware short-circuit detection of MHW-024. | MEA-004, EST-001, F3 |
| MHW-033 | Current and voltages shall be sampled simultaneously (same ADC conversion) for power and resistance calculations. | EST-004 |

### 3.5 Insulation monitoring

| ID | Requirement | From |
|---|---|---|
| MHW-040 | The master shall measure the insulation resistance of HV+ and HV− to protective earth (PE) in the range **10 kΩ…10 MΩ**, with the pack connected or disconnected. | SAF-016, F8 |
| MHW-041 | The master shall have a PE terminal. The measurement shall inject only limited current (**≤ 1 mA**) and be switchable off with `iso_en` (in case it interferes with the insulation and residual-current monitoring of the transformerless inverter). | SAF-016 |

### 3.6 Communication and user interface

| ID | Requirement | From |
|---|---|---|
| MHW-050 | CAN to the inverter through one isolated transceiver (reinforced isolation, e.g. ISOW1044 with integrated supply); ESD protection and connector shield referenced to the CAN domain only; 120 Ω termination switchable (jumper or MCU). | COM-001, F4 |
| MHW-051 | The CAN transceiver shall support silent (listen-only) operation for sniffing. | COM-007 |
| MHW-052 | The CAN connector shall be pin-compatible with the cable of the existing GCE BMS (RBMS07S70S50A) to the inverter. | COM-001 |
| MHW-053 | Wi-Fi/ESP-NOW antenna placement (on-module PCB antenna) for ≥ 5 m range to all slaves through the battery rack. | COM-002 |
| MHW-054 | LEDs (status, error, contactor states), buzzer, reset and boot buttons, USB-C (flashing/console), UART test header. | – |
| MHW-055 | Real-time clock with backup (or NTP with fallback) for timestamps in logs. | SAF-014 |
| MHW-056 | Non-volatile storage for `log_days` (≤ **7 days**) of 1-minute data (pack values and all cell voltages/temperatures, ≈ 400 B/min → ≈ 4 MB for 7 days) plus the complete fault log → **ESP32-S3-WROOM-1-N16R8** (16 MB flash; the N8R8 has only ≈ 3…4 MB left after two OTA slots). Long-term history is kept in Home Assistant. | SAF-014, CFG-007 |

### 3.7 Insulation, environment, manufacturing

| ID | Requirement | From |
|---|---|---|
| MHW-060 | Clearance/creepage per SAF-013: **reinforced for ≥ 600 V working voltage** between the HV domains (HV−, HV+) and the LV domain, CAN domain, PE and enclosure; **at least basic for 600 V** between HV− and HV+. Guide values for the PCB (IEC 60664-1, pollution degree 2, to be confirmed in the design): reinforced ≈ 6.4 mm creepage / 5.5 mm clearance; components crossing a reinforced barrier need a package with at least this creepage (e.g. wide-body SOIC-16W). | SAF-013 |
| MHW-061 | Operating ambient 0…40 °C, indoors, non-condensing. | HW-004 |
| MHW-062 | Manufacturable by JLCPCB; the power path (bus bars, heatsink) may be mechanical parts outside the PCB assembly. | HW-003 |

### 3.8 Protection of the power path

| ID | Requirement | From |
|---|---|---|
| MHW-070 | Each pole switch shall have an overvoltage clamp (TVS string or varistor) that absorbs the energy of the loop inductance at short-circuit turn-off (**≥ 0.5 J**, ½ L I² at 3 µH, 400 A, with margin) and keeps the MOSFET voltage below 1200 V. | SAF-004 |
| MHW-071 | The gate drivers shall have **desaturation (DESAT) short-circuit detection with soft turn-off** (1ED3860MC12M, MHW-022), in addition to the current-sensor threshold of MHW-024. In a back-to-back pair DESAT can only watch one MOSFET: it shall watch the MOSFET that conducts forward in the **discharge** direction (a short circuit behind the BMS can only be fed by the pack); the charge direction is covered by MHW-024. Blanking time longer than the turn-on V<sub>DS</sub> fall time (closing into the precharged DC link). The short-circuit turn-off shall be verified: the current reached at turn-off (loop inductance **1…3 µH**) shall be inside the pulse and short-circuit ratings of the SCT020H120G3AG. | SAF-004 |

---

## 4. Software requirements

### 4.1 States and protection

| ID | Requirement | From |
|---|---|---|
| MSW-001 | States: INIT → STANDBY (pack disconnected) → PRECHARGE → CONNECTED → (DERATED) → FAULT (latched); plus SERVICE (configuration, calibration) and SNIFF (CAN listen-only, pack disconnected). | SAF-001, COM-007 |
| MSW-002 | At boot all outputs shall be in their safe state before any other initialisation; the HV enable (MHW-023) shall only be set after the self test. | SAF-012 |
| MSW-003 | The protection functions (SAF-007…SAF-010, SAF-016) shall run every **100 ms** independently of communication with Home Assistant/web UI. | COM-006 |
| MSW-004 | Disconnect sequence: SiC off → wait until current ≈ 0 → contactors open → verify via feedback. Connect sequence (every contactor switches without current): HV− main contactor → BOT SiC on → precharge contactor (precharge resistor bridges TOP SiC and HV+ main contactor) → wait for `precharge_dv` → HV+ main contactor → TOP SiC on → precharge contactor off. | SAF-002, SAF-006 |
| MSW-005 | A hardware watchdog shall reset the master if the firmware hangs for more than **1 s**, which opens all switches (MHW-023, MHW-025). | SAF-012 |
| MSW-006 | Faults shall be latched and logged; critical faults require a user reset (web UI or Home Assistant, authenticated). | SAF-014 |
| MSW-007 | Precharge plausibility: abort the precharge when the inverter voltage has not reached **50 % of the pack voltage after 1 s**; wait **≥ 60 s** between retries (resistor cooling). The DC-link capacitance shall be estimated from the precharge curve and logged. | SAF-006 |
| MSW-008 | Low-power state per SAF-017: master sleeps (Wi-Fi off), wakes every 10 min, collects slave data, publishes, and stays awake on user request (button or web UI within the wake window). Charge-only reconnection per SAF-018. | SAF-017, SAF-018 |
| MSW-009 | Gate-driver bring-up at every power-up and after any gate-supply loss **(P)**: assign the I²C addresses (one driver at a time via RDYC/IN), write and read back the configuration (DESAT threshold/blanking/filter, soft-off current and fault-off mode set explicitly, soft UVLO ≈ 16 V, VEE2 UVLO off for −3 V), set `USER_OK`; the HV enable is only allowed after a successful read-back. | SAF-012, MHW-022, MHW-071 |

### 4.2 Slave management

| ID | Requirement | From |
|---|---|---|
| MSW-010 | The master shall discover the slaves, check that `modules_count` slaves with unique addresses are present, distribute the configuration and start operation only when all slaves confirmed it. | CFG-001, COM-003 |
| MSW-011 | The master shall provide the time base for synchronised measurement (MEA-008). | MEA-008 |
| MSW-012 | Slave timeouts per SAF-010. | SAF-010 |
| MSW-013 | The master shall compute the common balancing target and send balancing commands to all slaves. | BAL-005 |

### 4.3 Inverter communication

| ID | Requirement | From |
|---|---|---|
| MSW-020 | The master shall emulate the inverter protocol of COM-001 (first choice BYD HVS/HVM CAN, fallback the GCE RBMS07S70S50A protocol), documented per COM-008. It shall stay silent until the inverter has sent its first frame and answer the identification request. | COM-001, COM-008 |
| MSW-021 | SNIFF mode: log all CAN frames with timestamps (≥ 1 ms resolution) to file, downloadable via web UI. | COM-007 |
| MSW-022 | Replay/test mode: send recorded or synthetic sessions on a test bus to verify the implementation. | COM-008 |
| MSW-023 | No frames from the inverter for `inverter_timeout` → allowed currents zero, then disconnect. | COM-001 |
| MSW-024 | The master firmware shall be a MicroPython build with ESP32 CAN (TWAI) support including listen-only mode (mainline has no ESP32 `machine.CAN`: PR #19461 or a user C module); receive timestamps are taken in the RX interrupt (`time.ticks_us()`). | COM-007, HW-001 |

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
| MOPEN-01 | *(closed in 0.4: ST SCT020H120G3AG, MHW-020)* |
| MOPEN-02 | *(closed in 0.3: master and 12 V coil supply from the whole pack via isolated HV DC/DC, MHW-001)* |
| MOPEN-03 | *(closed in 0.3: ACS71240LLCBTR-050B3, MHW-032)* |
