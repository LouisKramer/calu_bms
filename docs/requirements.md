# CALU BMS – System Requirements

| | |
|---|---|
| Status | Draft 0.7 |
| Scope | Battery management system for a stationary high-voltage LFP home storage |
| Related | [Slave requirements](slave_requirements.md), [Master requirements](master_requirements.md), [Master concept review](master_concept_review.md), [Plausibility check](plausibility_check.md) |
| Earlier work | branches `playground` (first prototypes), `slave-hw-2.0.1.0`, `slave-hw-3.0.0.0` |

Conventions:
- **shall** = mandatory, **should** = recommended, **may** = optional.
- Every requirement has an ID so tests, design and firmware can refer to it.
- `parameter_name` refers to a configuration parameter in chapter 9 (default, range, unit).
  Values written directly in a requirement are fixed design values, not configurable.
- Values marked **(P)** are new proposals that still need confirmation.

---

## 1. System overview

```
                         CAN                    ESP-NOW (wireless)
  Inverter  <──────────────────────>  MASTER  <───────────────────>  SLAVE 1 … SLAVE 10
  (GoodWe GW8KN-ET)                     │                              │ (one per 16S module)
                                        │ 2-stage disconnect           │ cell voltages, temperatures,
  HV+ ──── fuse ── SiC ── relay ────────┤ current, pack voltage        │ passive balancing,
  HV- ─────────────── SiC ── relay ─────┤ SOC/SOH, protection          │ optional active balancer
                                        │ Wi-Fi: web UI, Home Assistant
                                        │ supplied from the whole pack (isolated HV DC/DC)
            8 modules (up to 10) × 16S LFP 350 Ah in series = 128S1P (up to 160S1P)
```

| Item | Value |
|---|---|
| Cells | LFP, 350 Ah, 128 in series (8 modules × 16S), 1P; hardware rated for up to 10 modules (160S) |
| Nominal voltage / energy | 128 × 3.2 V ≈ 410 V, ≈ 143 kWh (160S: ≈ 512 V, ≈ 179 kWh) |
| Pack voltage range | 128S: 320 V (2.50 V/cell) … 467 V (3.65 V/cell); 160S: 400 … 584 V |
| Current (BMS rating) | 25 A charge, 25 A discharge, continuous |
| Inverter | GoodWe GW8KN-ET (ET PLUS+ 16A series, [datasheet](datasheets/GW_ET%20PLUS+%20(16A)_Datasheet_EMEA-DE.pdf)): battery 180…600 V, 25 A continuous charge/discharge, 9.6 kW, CAN, transformerless (not isolated) |
| Installation | indoors, heated, not below 0 °C |

The planned pack (128S, 320…467 V) and the maximum of 10 modules (160S, up to 584 V) lie inside the battery
voltage range of the GW8KN-ET, and the BMS current rating matches the inverter's 25 A. A pack with fewer
modules is possible as long as its voltage stays inside the inverter range (`inv_v_min`, `inv_v_max`,
CFG-003); with the defaults this is the case from 4 modules (64S) on.

---

## 2. System requirements

| ID | Requirement |
|---|---|
| SYS-001 | The BMS shall monitor and protect a pack of up to 160 LFP cells in series, built from up to 10 modules of up to 16S. |
| SYS-002 | The BMS shall consist of one master and one slave per module. |
| SYS-003 | The system shall be expandable by adding modules in series up to the hardware rating (10 modules, 600 V) and the voltage range of the connected inverter (`inv_v_min`, `inv_v_max`). Each module shall support 4–16 cells (`cells_per_module`). |
| SYS-004 | The BMS hardware shall be rated for 25 A continuous charge and discharge current. The limits actually sent to the inverter (`i_charge_max`, `i_discharge_max`) shall never exceed the cell, BMS or inverter ratings. |
| SYS-005 | All operating parameters shall be configurable without changing firmware, as defined in chapter 9. |
| SYS-006 | Firmware of master and slaves shall be updatable without opening the modules (OTA). |
| SYS-007 | The number of modules (`modules_count`) shall be configurable, so the pack can be built up step by step (fewer modules) and later extended up to 10 modules. |

## 3. Safety and protection

| ID | Requirement |
|---|---|
| SAF-001 | The master shall disconnect the pack from the inverter (both poles) when any protection limit is exceeded. |
| SAF-002 | Disconnection shall be two-stage: **stage 1** SiC semiconductor switches open the current fast; **stage 2** relays/contactors then open galvanically at (near) zero current. Relays shall not be required to break load current. |
| SAF-003 | The stage-1 switches shall block current in both directions (charge and discharge). |
| SAF-004 | Short-circuit current shall be interrupted by stage 1 within **10 µs**, independently of the firmware (hardware comparator, fixed threshold). |
| SAF-005 | The pack shall have a DC fuse rated for the pack voltage as backup for a failed (shorted) stage-1 switch and for cable short circuits; its DC breaking capacity shall exceed the prospective short-circuit current of the pack (≈ 12 kA → **≥ 20 kA (P)**). |
| SAF-006 | Connecting the pack to the inverter shall use precharge of the inverter DC-link capacitance; the master shall close only when the voltage difference is below `precharge_dv` within `precharge_timeout`. |
| SAF-007 | Cell voltage protection: a cell above `cell_ov_trip` or below `cell_uv_trip` for longer than `cell_v_trip_delay` shall disconnect the pack. Above `cell_ov_warn` / below `cell_uv_warn` the allowed charge / discharge current shall be reduced to zero before a trip occurs. |
| SAF-008 | Temperature protection: charging only between `t_charge_min` and `t_charge_max`, discharging only between `t_discharge_min` and `t_discharge_max`; outside these limits the respective current shall be set to zero, and the pack disconnected if the limit is exceeded by more than `t_trip_margin`. Charging below 0 °C shall never be allowed (no cell heating). |
| SAF-009 | Over-current protection: current above `oc1_level` for `oc1_time` or above `oc2_level` for `oc2_time` shall disconnect the pack; short circuit per SAF-004. |
| SAF-010 | Loss of communication with any slave for longer than `slave_timeout_fault` shall be treated as a fault (allowed currents set to zero); after `slave_timeout_trip` the pack shall be disconnected. |
| SAF-011 | Every slave shall switch off all balancing when it receives no valid command from the master within `slave_bal_timeout`, and during its own reset (hardware default off). |
| SAF-012 | The safe state (relays open, balancing off) shall also be reached on master power loss, reset or firmware crash (fail-safe hardware defaults, watchdog). |
| SAF-013 | Slave electronics float at the potential of their module; the master's HV domains float at the pack potential. With the transformerless inverter the pack potential to earth is set by the inverter. All insulation shall therefore be designed for the inverter's maximum battery voltage (600 V DC): **reinforced, ≥ 600 V working voltage** between HV circuits and everything that can be touched or is connected to other equipment (master LV domain, CAN, USB, PE, enclosure); **at least basic for 600 V (P)** between HV circuits that are not accessible (e.g. HV− and HV+ domains of the master). Service USB on a board in the stack shall only be used through an isolator rated **≥ 1 kV**. |
| SAF-014 | Faults shall be latched and logged; restart after a protection trip shall require the fault to be cleared, and for critical faults (cell over-voltage, short circuit) an explicit user reset. |
| SAF-015 | Protection limits shall not depend on the inverter respecting the transmitted current/voltage limits: the BMS disconnects by itself. |
| SAF-016 | The master shall monitor the insulation resistance of the pack (HV+ and HV−) to protective earth. Below `iso_warn` an alarm shall be raised; below `iso_trip` the action `iso_trip_action` (alarm or disconnect) shall be taken. The GW8KN-ET is transformerless and has its own insulation and residual-current monitoring; if the two measurements interfere, the BMS measurement shall be switched off with `iso_en`. |
| SAF-017 | After an under-voltage trip, and whenever the pack is disconnected with a cell below `cell_uv_warn`, master and slaves shall enter a low-power state so the BMS itself does not deep-discharge the cells: slave **≤ 1 mA (P)** average from its module, master **≤ 0.5 W (P)** from the pack (incl. HV DC/DC no-load loss); they wake up periodically (**every 10 min (P)**) to measure and report. |
| SAF-018 | After an under-voltage trip a user reset shall allow reconnecting **for charging only** (discharge limit 0) until all cells are above `cell_uv_warn` again. |

## 4. Measurement

| ID | Requirement |
|---|---|
| MEA-001 | Every cell voltage shall be measured with an accuracy of **±2 mV** over the operating temperature range, after calibration. |
| MEA-002 | All cells of the pack shall be measured at least every `meas_period` (≤ 1 s). |
| MEA-003 | Each slave shall measure up to 4 temperatures per module (`temp_sensor_count`, cells/bus bars) plus its own board temperature. |
| MEA-004 | The master shall measure the pack current, both directions, with a Hall current sensor: accuracy **±1 %** of reading after calibration, offset error **≤ 150 mA** after automatic zeroing (every time the pack is disconnected the current is exactly zero and the offset shall be re-measured). |
| MEA-005 | The master shall measure the pack voltage (battery side) and the inverter-side voltage (for precharge, SAF-006). |
| MEA-006 | The slave measurement shall not load the cells unevenly; the current a slave draws from its cells shall be equal for all cells of a module, and equal between modules within **1 mA**. |
| MEA-007 | Measurement shall detect open tap wires and implausible values (e.g. sum of cells vs. module voltage, tolerance `plaus_tol`) and report them as faults. |
| MEA-008 | Cell voltages of all slaves shall be sampled time-synchronous within **100 ms**, so that pack-level calculations use matching data. |

## 5. Balancing

| ID | Requirement |
|---|---|
| BAL-001 | Each slave shall provide passive balancing for each cell. |
| BAL-002 | Passive balancing current shall be **≥ 150 mA** per cell; the bleed resistors shall stay within their rating at continuous operation of all channels. |
| BAL-003 | Each slave shall provide an interface for an optional active balancing module (enable + switching-clock signal), so active balancing can be added later without changing the slave. |
| BAL-004 | Balancing shall be paused during cell voltage measurement. |
| BAL-005 | The master shall coordinate balancing across all modules (common target voltage), so that modules are balanced to each other and not only internally. |
| BAL-006 | Balancing shall start only above `bal_start_v` and for cells more than `bal_delta` above the target; passive and active balancing shall be enabled separately (`bal_passive_en`, `bal_active_en`). |
| BAL-007 | *(removed in 0.6: the master is supplied from the whole pack, HW-005, so it loads all cells equally and needs no compensation)* |

## 6. State estimation

| ID | Requirement |
|---|---|
| EST-001 | The master shall estimate the state of charge (SOC) of the pack with an error of **< 5 %**, using coulomb counting with correction at rest (`soc_rest_current`, `soc_rest_time`) and at full charge (`full_cell_v`, `full_current`). Because the current-sensor offset drift adds up to ≈ 1 %/day, the master shall request a full charge when none was detected within `full_charge_interval` **(P)**. |
| EST-002 | The master shall estimate the state of health (SOH, remaining capacity relative to `cell_capacity_ah`). |
| EST-003 | SOC and SOH shall be stored non-volatile and survive a power loss. |
| EST-004 | The master shall calculate the allowed charge/discharge current and voltage limits continuously from cell voltages, temperatures, SOC (`charge_taper`) and configuration, and send them to the inverter. |

## 7. Communication and interfaces

| ID | Requirement |
|---|---|
| COM-001 | The master shall communicate with the inverter over CAN using a battery protocol the GoodWe inverter accepts. First choice **(P)**: the **BYD HVS/HVM CAN protocol** (listed as compatible by GoodWe, documented in open-source code, 500 kbit/s, see plausibility check P14). Fallback and cross-check: the protocol of the existing BMS (**GCE RBMS07S70S50A**), reverse engineered from its traffic with the inverter (COM-007, OPEN-02). |
| COM-002 | Master and slaves shall communicate wirelessly (ESP-NOW), which also provides galvanic isolation between modules. |
| COM-003 | Each slave shall have a hardware-configurable module address (position in the stack). |
| COM-004 | The master shall publish all measured values, states and faults to Home Assistant (MQTT). |
| COM-005 | The master shall provide a web interface over Wi-Fi for status, configuration and fault reset. |
| COM-006 | The safety function of the master shall not depend on Wi-Fi or Home Assistant being available. |
| COM-007 | The master hardware shall support a **listen-only CAN mode** (no ACK, no transmission) and log all frames with timestamps, so the existing BMS ↔ inverter traffic can be recorded without disturbing it. |
| COM-008 | The protocol implementation shall be documented (message IDs, cycle times, scaling, meaning, timeouts) and verified by replaying recorded sessions before it is used with the real inverter. |
| COM-009 | The BMS shall stay within the behaviour of the original BMS on the bus (cycle times, value ranges); unknown fields shall be sent with the values observed from the original BMS. |

## 8. Hardware constraints

| ID | Requirement |
|---|---|
| HW-001 | Master and slaves shall use the ESP32-S3 (MicroPython firmware). |
| HW-002 | Each slave shall be supplied from its own module (whole module voltage, all cells loaded equally). |
| HW-003 | All boards shall be manufacturable by JLCPCB (PCB + assembly). |
| HW-004 | Operating ambient temperature: **0…40 °C**, indoors, non-condensing. |
| HW-005 | The master shall be mountable at any position of the stack. It shall be supplied from the whole pack (battery side of the disconnect, so it also runs with the pack disconnected) through an isolated HV DC/DC, so its consumption loads all cells equally. |

---

## 9. Configuration

### 9.1 General

| ID | Requirement |
|---|---|
| CFG-001 | The configuration shall be held by the master and distributed to the slaves. Each slave shall confirm the received configuration (version number + checksum); the master shall not start operation while a slave runs a different configuration version. |
| CFG-002 | The configuration shall be stored non-volatile on master and slaves and survive power loss and firmware updates. |
| CFG-003 | Every parameter shall have a default, a minimum, a maximum and a unit. Values outside the range shall be rejected. Cross-checks shall be enforced (e.g. warning level inside trip level, `oc1_level` < `oc2_level`, current limits ≤ hardware rating, and the pack voltage inside the inverter range: total cells × `discharge_cell_v` ≥ `inv_v_min` and total cells × `cell_ov_trip` ≤ `inv_v_max`). |
| CFG-004 | Parameters marked **S** (safety) shall only be changed while the pack is disconnected and after authentication; all other parameters may be changed during operation. |
| CFG-005 | Hardware ratings (25 A, 10 modules, 16 cells/module, short-circuit threshold) are fixed and not configurable; parameter ranges shall be limited to them. |
| CFG-006 | It shall be possible to restore the defaults and to export/import the complete configuration as a file (JSON). |
| CFG-007 | Every configuration change shall be logged with time, parameter, old and new value. |
| CFG-008 | Configuration changes shall be possible via the web interface (COM-005) and via Home Assistant (MQTT, COM-004). Both paths shall apply the same validation (CFG-003) and the same rules for safety parameters (CFG-004); the MQTT connection shall be authenticated (user/password, TLS should be supported). |
| CFG-009 | Calibration data of a slave (measurement gain/offset) is not part of the configuration: it shall be stored on the slave itself and survive configuration resets. |

### 9.2 Parameters

Defaults are for the full pack (8 × 16S LFP 350 Ah) on the GW8KN-ET.

**Pack**

| Parameter | Default | Range | Unit | S | Used in |
|---|---|---|---|---|---|
| `modules_count` | 8 | 1 … 10 | – | S | SYS-007 |
| `cells_per_module` (per module) | 16 | 4 … 16 | – | S | SYS-003 |
| `cell_capacity_ah` | 350 | 10 … 1000 | Ah | | EST-002 |
| `inv_v_min` (lowest battery voltage of the inverter) | 180 | 0 … 600 | V | S | SYS-003, CFG-003 |
| `inv_v_max` (highest battery voltage of the inverter) | 600 | 100 … 600 | V | S | SYS-003, CFG-003 |

**Cell voltage**

| Parameter | Default | Range | Unit | S | Used in |
|---|---|---|---|---|---|
| `cell_ov_trip` | 3.65 | 3.50 … 3.65 | V | S | SAF-007 |
| `cell_ov_warn` | 3.55 | 3.40 … `cell_ov_trip` − 0.02 | V | S | SAF-007 |
| `cell_uv_warn` | 2.80 | `cell_uv_trip` + 0.05 … 3.20 | V | S | SAF-007 |
| `cell_uv_trip` | 2.50 | 2.50 … 3.00 | V | S | SAF-007 |
| `cell_v_trip_delay` | 3 | 1 … 10 | s | S | SAF-007 |
| `cell_v_hyst` | 0.05 | 0.01 … 0.20 | V | | warning release |
| `charge_cell_v` (charge target sent to inverter) | 3.50 | 3.40 … 3.60 | V/cell | S | EST-004 |
| `discharge_cell_v` (discharge end sent to inverter) | 2.90 | 2.80 … 3.20 | V/cell | S | EST-004 |

**Temperature**

| Parameter | Default | Range | Unit | S | Used in |
|---|---|---|---|---|---|
| `t_charge_min` | 0 | 0 … 10 | °C | S | SAF-008 |
| `t_charge_max` | 45 | 30 … 55 | °C | S | SAF-008 |
| `t_discharge_min` | −10 | −20 … 0 | °C | S | SAF-008 |
| `t_discharge_max` | 55 | 40 … 60 | °C | S | SAF-008 |
| `t_warn_margin` (current derating starts this far before a limit) | 5 | 2 … 10 | K | | EST-004 |
| `t_trip_margin` | 5 | 2 … 10 | K | S | SAF-008 |
| `t_board_max` (slave/master board) | 85 | 60 … 100 | °C | S | SAF-008 |
| `t_switch_max` (SiC switches/heatsink on the master) | 100 | 60 … 125 | °C | S | SAF-008 |
| `temp_sensor_count` (per module) | 4 | 0 … 4 | – | | MEA-003 |

**Current**

| Parameter | Default | Range | Unit | S | Used in |
|---|---|---|---|---|---|
| `i_charge_max` | 25 | 0 … 25 | A | S | SYS-004 |
| `i_discharge_max` | 25 | 0 … 25 | A | S | SYS-004 |
| `oc1_level` | 27 | 10 … 29 | A | S | SAF-009 |
| `oc1_time` | 10 | 1 … 60 | s | S | SAF-009 |
| `oc2_level` (below the 50 A hardware short-circuit threshold) | 30 | 15 … 45 | A | S | SAF-009 |
| `oc2_time` | 1 | 0.5 … 5 (P) | s | S | SAF-009 |
| `charge_taper` (allowed charge current vs. SOC) | 0 %→100 %, 90 %→100 %, 95 %→40 %, 98 %→20 %, 99 %→8 %, 100 %→0 % | table, 2 … 10 points, monotonic | %, % | | EST-004 |

**Precharge and disconnect**

| Parameter | Default | Range | Unit | S | Used in |
|---|---|---|---|---|---|
| `precharge_dv` | 10 | 2 … 20 | V | S | SAF-006 |
| `precharge_timeout` | 5 | 1 … 30 | s | S | SAF-006 |
| `precharge_retries` | 2 | 0 … 5 | – | S | SAF-006 |

**Insulation monitoring**

| Parameter | Default | Range | Unit | S | Used in |
|---|---|---|---|---|---|
| `iso_en` | true | true / false | – | S | SAF-016 |
| `iso_warn` | 500 | 100 … 1000 | Ω/V | S | SAF-016 |
| `iso_trip` | 100 | 50 … 500 | Ω/V | S | SAF-016 |
| `iso_trip_action` | disconnect | alarm / disconnect | – | S | SAF-016 |
| `iso_period` | 10 | 1 … 60 | s | | SAF-016 |

**Communication and timeouts**

| Parameter | Default | Range | Unit | S | Used in |
|---|---|---|---|---|---|
| `slave_timeout_fault` | 5 | 2 … 30 | s | S | SAF-010 |
| `slave_timeout_trip` | 30 | 10 … 120 | s | S | SAF-010 |
| `slave_bal_timeout` | 30 | 10 … 120 | s | S | SAF-011 |
| `inverter_timeout` (no CAN frames from inverter → currents zero) | 10 | 2 … 60 | s | S | COM-001 |
| `can_bitrate` | 500 | 125, 250, 500, 1000 | kbit/s | | COM-001 (confirm by sniffing) |
| `espnow_channel` (auto = channel of the Wi-Fi access point, slaves scan) | auto (P) | auto, 1 … 13 | – | | COM-002 |

**Measurement**

| Parameter | Default | Range | Unit | S | Used in |
|---|---|---|---|---|---|
| `meas_period` | 1.0 | 0.5 … 1.0 | s | | MEA-002 |
| `plaus_tol` (cell sum vs. module voltage) | 1.0 | 0.2 … 5.0 | % | | MEA-007 |

**Balancing**

| Parameter | Default | Range | Unit | S | Used in |
|---|---|---|---|---|---|
| `bal_passive_en` | true | true / false | – | | BAL-006 |
| `bal_active_en` | false | true / false | – | | BAL-006 |
| `bal_start_v` | 3.40 | 3.20 … 3.60 | V | | BAL-006 |
| `bal_delta` | 0.010 | 0.003 … 0.100 | V | | BAL-006 |
| `bal_active_freq` (switching clock for the active balancer) | 1000 | 100 … 5000 | Hz | | BAL-003 |

**State estimation**

| Parameter | Default | Range | Unit | S | Used in |
|---|---|---|---|---|---|
| `soc_rest_current` (above the current-sensor offset) | 1.0 | 0.3 … 5 | A | | EST-001 |
| `soc_rest_time` | 30 | 5 … 240 | min | | EST-001 |
| `full_cell_v` (highest cell for "full" detection) | 3.45 | 3.40 … 3.60 | V | | EST-001 |
| `full_current` (charge current below which "full" is detected) | 5 | 1 … 10 | A | | EST-001 |
| `full_charge_interval` (request a full charge if none within; 0 = off) (P) | 7 | 0 … 30 | days | | EST-001 |

**User interfaces**

| Parameter | Default | Range | Unit | S | Used in |
|---|---|---|---|---|---|
| `wifi_ssid`, `wifi_password` | – | text | – | | COM-005 |
| `mqtt_host`, `mqtt_port`, `mqtt_user`, `mqtt_password` | –, 1883, –, – | text / 1 … 65535 | – | | COM-004 |
| `mqtt_prefix` | `calu_bms` | text | – | | COM-004 |
| `mqtt_period` | 10 | 1 … 300 | s | | COM-004 |
| `web_password` | – (must be set at commissioning) | text | – | | CFG-004 |

---

## 10. Open points

| ID | Question |
|---|---|
| OPEN-02 | Inverter protocol: test the BYD HVS/HVM emulation with the GW8KN-ET (battery selection in SolarGo, inverter firmware version) and sniff the GCE RBMS07S70S50A as cross-check: CAN bit rate, connector pinout, wiring/termination for tapping the bus. Capture plan: idle, charge, discharge, full, empty, BMS fault, BMS disconnected (inverter timeout behaviour). |

Closed: OPEN-01 (GW8KN-ET: 180…600 V, 25 A → full 128S pack fits, current rating reduced to 25 A),
OPEN-07 (power path: 25 A instead of 100 A, heatsinks on the SiC switches, see master MOPEN-01),
OPEN-08 (insulation monitoring can be switched off with `iso_en` if it interferes with the inverter),
OPEN-09 (master supplied from the whole pack, HW-005; BAL-007 removed),
OPEN-10 (insulation designed for 600 V working voltage, SAF-013; maximum raised from 8 to 10 modules).
