# CALU BMS – Plausibility Check of the Requirements

| | |
|---|---|
| Status | 0.2 (decisions of 2026-11-20 in section 4) |
| Checked | [System requirements](requirements.md) 0.6, [Slave requirements](slave_requirements.md) 0.3, [Master requirements](master_requirements.md) 0.4 |
| Result | Requirements are feasible. Some need a change or an added requirement, marked **(P)** in the requirement documents (section 3). |

Legend: ✅ plausible as specified, ⚠️ plausible with a condition or small change, ❌ not feasible as specified → changed.

Estimates use datasheet values where cited and typical values otherwise; they are meant to show the
order of magnitude and have to be confirmed in the detailed design.

---

## 1. Summary

| # | Topic | Requirements | Result | Action |
|---|---|---|---|---|
| P1 | ESP32-S3 + MicroPython as master | HW-001, MSW-003 | ⚠️ | Feasible; GC pauses → `oc2_time` ≥ 0.5 s, all fast protection in hardware |
| P2 | Data logging on the master | MHW-056 | ❌ | 30 days of full cell data do not fit into flash → summary data, N16R8 module or microSD |
| P3 | Wi-Fi and ESP-NOW on one radio | COM-002, COM-005, `espnow_channel` | ❌ | ESP-NOW must use the channel of the Wi-Fi access point → `espnow_channel` = auto |
| P4 | ESP-NOW with 10 slaves | MEA-002, MEA-008, SAF-010 | ✅ | Airtime < 1 %; encrypted-peer limit must be raised |
| P5 | Cell voltage ±2 mV | MEA-001, SHW-002 | ✅ | Feasible with 24-bit ADC + precision reference + calibration |
| P6 | Slave consumption ≤ 2 W, equal within 1 mA | SHW-043 | ✅ | ≈ 0.5 W expected; radio permanently on |
| P7 | Hall current sensor and SOC < 5 % | MEA-004, EST-001 | ⚠️ | Needs a full charge at least every ≈ 4 days → new `full_charge_interval` |
| P8 | SiC conduction loss and cooling | MHW-020 | ✅ | ≈ 70…80 W total at 25 A; heatsink ≈ 0.4 K/W |
| P9 | Short-circuit turn-off | SAF-004, MHW-024 | ⚠️ | Current at turn-off ≈ 400 A → overvoltage clamp and verification of the SiC pulse rating |
| P10 | Pack fuse | SAF-005, MHW-028 | ⚠️ | Prospective short-circuit current ≈ 12 kA → breaking capacity ≥ 20 kA DC |
| P11 | Precharge | SAF-006, MHW-026 | ⚠️ | Up to ≈ 170 J per precharge; shorted inverter input would burn the resistor → plausibility abort |
| P12 | Contactors at 600 V DC | MHW-025, MHW-027 | ✅ | EV-type HV contactors; must break both directions in an emergency |
| P13 | Isolation 600 V reinforced, isolated parts (F12) | SAF-013, MHW-022, MHW-060 | ⚠️ | Reinforced only where needed; 1ED3121MU12H → MC12H, gate supply QA123C-1803R3, master supply PV15-27B12R3 (15 W) |
| P14 | Inverter protocol and CAN in MicroPython | COM-001, COM-007 | ⚠️ | BYD HVS/HVM CAN emulation first, sniffing as fallback; custom MicroPython build with ESP32 CAN |
| P15 | HV voltage measurement ±0.5 % up to 600 V | MHW-031 | ✅ | Divider chain of ≥ 6 resistors, calibration |
| P16 | Insulation monitoring at 600 V | SAF-016, MHW-040 | ✅ | Trip 100 Ω/V = 60 kΩ, warn 500 Ω/V = 300 kΩ inside 10 kΩ…10 MΩ |
| P17 | Deep discharge by the BMS itself | – (missing) | ❌ | New: low-power state after under-voltage trip, charge-only recovery |
| P18 | Radio through a metal rack | SHW-051, MHW-053 | ⚠️ | External antenna option proposed – **not accepted** (section 4) |

---

## 2. Details

### P1 – ESP32-S3 and MicroPython as master ⚠️

Load per 100 ms protection cycle: 10 slave messages (≈ 160 cell voltages, 50 temperatures), limit checks,
current integration, CAN frames every 100 ms…1 s. That is a few thousand Python operations, ≈ 1…5 ms on the
240 MHz core. Web UI, MQTT (with TLS: ≈ 40 kB RAM, handshake 1…3 s) and logging run in asyncio tasks; Wi-Fi
runs in ESP-IDF on the second core. RAM (8 MB PSRAM) and CPU are sufficient.

Risk: the MicroPython garbage collector stops the interpreter; with a large PSRAM heap a collection can take
tens of milliseconds and more. Consequences:
- every protection that must act faster than ≈ 0.5 s stays in hardware (MHW-024 short circuit, MHW-023 enable,
  watchdog) – already required;
- `oc2_time` minimum raised from 0.1 s to **0.5 s (P)**; the hardware threshold (50 A) covers faster events;
- `gc.collect()` called explicitly once per cycle so collections are short and predictable.

### P2 – Data logging ❌

MHW-056 asks for 30 days of 1-minute data. Full record: pack values ≈ 32 B + 160 cells × 2 B + 50 temperatures
≈ 400 B → 30 × 1440 × 400 B ≈ **17 MB**. The ESP32-S3-WROOM-1-N8R8 has 8 MB flash, of which ≈ 3…4 MB remain
after two OTA firmware slots.

Change **(P)**: 30 days of pack data plus a per-module summary (min/max/mean cell voltage, max temperature,
balancing): ≈ 32 B + 10 × 8 B ≈ 112 B/min → ≈ 4.8 MB; full cell data for the last 24 h ≈ 0.6 MB. This needs the
**ESP32-S3-WROOM-1-N16R8** (16 MB flash) or a microSD card. The long-term history is kept in Home Assistant
(recorder/InfluxDB). Flash wear: ≈ 160 kB/day on a ≈ 6 MB LittleFS area → far below the erase-cycle limit.

### P3 – Wi-Fi and ESP-NOW on one radio ❌

The ESP32 has one radio. While the master is connected to the Wi-Fi access point (MQTT, web UI), ESP-NOW can
only use the **channel of the access point**. A fixed `espnow_channel` does not work if the router changes
its channel (automatic channel selection).

Change **(P)**: `espnow_channel` = `auto` (default): the master uses the access point's channel; slaves that
lose the master scan channels 1…13 (≈ 13 × 100 ms) and lock to the master's beacon. This is far below
`slave_timeout_fault` (5 s). A fixed channel stays selectable for installations without Wi-Fi. Recommended:
fix the router's 2.4 GHz channel.

### P4 – ESP-NOW with 10 slaves ✅

Per slave and second: one data message (≈ 16 × 2 B cells + temperatures + status ≈ 100 B, max. payload 250 B)
→ 10 messages/s ≈ 10 × 0.5 ms airtime ≈ 0.5 % of the channel. Synchronisation (MEA-008, 100 ms) via a
broadcast trigger plus the synchronised time base (SWS-024); a lost broadcast is covered by the time base.

Condition: SWS-020 requires encryption. ESP-IDF allows 20 peers, but by default only 7 encrypted peers
(configurable up to 17). With 10 slaves the firmware build must raise this limit, or the master uses
encrypted unicast only for the slaves and broadcast messages are authenticated in the application (HMAC).

### P5 – Cell voltage ±2 mV ✅

±2 mV at 3.3 V is 0.06 %. Error budget for a 24-bit ADC (e.g. ADS1220) with precision reference (e.g.
REF5040), flying capacitor or equivalent multiplexer, after a per-board calibration at 25 °C:

| Source | Value | Error at 3.3 V |
|---|---|---|
| Reference drift, 0…40 °C (±15 K from calibration), 3 ppm/K (A grade) / 8 ppm/K (I grade) | 45 / 120 ppm | 0.15 / 0.4 mV |
| ADC gain drift, offset drift, INL (≤ 15 ppm FS) | ≈ 30 ppm | ≈ 0.1 mV |
| Noise at ≈ 300 SPS, averaged | < 10 µV | < 0.01 mV |
| Multiplexer leakage, charge injection, dielectric absorption (film capacitor) | estimate | ≤ 0.5 mV |
| Calibration reference (6½-digit DMM) | ≈ 30 ppm | 0.1 mV |
| **Sum (worst case)** | | **≈ 1.2 mV** |

A cell-monitor IC (e.g. ADI LTC681x/ADBMS family, total measurement error ≈ 1.2…2.2 mV) would also meet the
requirement.

### P6 – Slave consumption ✅

ESP32-S3 with the radio permanently on (receive) ≈ 100 mA, measurement + logic ≈ 10 mA at 3.3 V → ≈ 0.36 W;
with a buck converter (≈ 80 %) ≈ 0.45 W, i.e. ≈ 9 mA from a 51 V module. SHW-043 (≤ 2 W) is met with margin.
Equality within 1 mA: unit-to-unit spread of the radio current (≈ ±10 %) and the converter efficiency
(≈ ±3 %) gives ≈ ±1 mA at 51 V. Radio power saving shall stay off so the load is constant. A remaining
difference of 1 mA is 24 mAh/day and is corrected by module balancing within minutes per day.

### P7 – Hall current sensor and SOC ⚠️

ACS71240LLCBTR-050B3: 26.4 mV/A, offset error ±15 mV (≈ ±0.57 A) over temperature, ±28 mV including lifetime
drift. Automatic zeroing whenever the pack is disconnected removes the initial offset; the remaining drift
between two zeroings (temperature change within 0…40 °C) is estimated at ±2…4 mV ≈ **±0.1…0.15 A**. MEA-004 is
plausible at its limit.

SOC effect: 0.15 A × 24 h = 3.6 Ah/day ≈ **1 % of 350 Ah per day**. EST-001 (< 5 %) therefore holds only if
SOC is re-anchored at least every ≈ 4 days. With LFP the open-circuit voltage is flat between ≈ 10 % and 90 %,
so rest correction works only near the ends; the reliable anchor is the full charge. In winter (little PV)
there may be no full charge for weeks.

Change **(P)**: new parameter `full_charge_interval` (default 7 days, range 0 = off … 30): when no full charge
was detected within the interval, the master requests a full charge from the inverter (charge target
`charge_cell_v`, also used for top balancing). EST-001 states the condition.

### P8 – SiC conduction loss and cooling ✅

SCT020H120G3AG: 18.5 mΩ at 25 °C, 37 mΩ at 175 °C (typ, V<sub>GS</sub> = 18 V); linear estimate ≈ 28 mΩ at
100 °C, ≈ 31 mΩ at 125 °C.

| Operating point | Per MOSFET | Per pole (2) | Total (4) |
|---|---|---|---|
| 25 A, T<sub>j</sub> = 100 °C | 17 W | 35 W | **70 W** |
| 25 A, T<sub>j</sub> = 125 °C | 19 W | 39 W | 78 W |
| 10 A, T<sub>j</sub> = 60 °C | 2.3 W | 4.6 W | 9 W |

25 A only occurs at low pack voltage: the GW8KN-ET is limited to 9.6 kW, i.e. 23.4 A at 410 V.

Thermal path per MOSFET (H²PAK-7 soldered to the PCB, heat through thermal vias and an insulating pad to a
heatsink below the board): R<sub>th,j-c</sub> 0.27 K/W + PCB with via array ≈ 1.2 K/W + insulating pad
≈ 0.5 K/W ≈ 2 K/W → ΔT<sub>j-hs</sub> ≈ 35 K at 17 W. For T<sub>j</sub> ≤ 100 °C at 40 °C ambient the heatsink
may reach 65 °C → **R<sub>th,hs-a</sub> ≤ 0.35…0.4 K/W** for one common heatsink (70 W), e.g. a finned extrusion
of ≈ 200 × 150 × 50 mm in natural convection, or a smaller heatsink with a fan. The insulating pad must be
rated for the HV potential of the drain tabs (P13). `t_switch_max` (100 °C at the heatsink sensor) fits.

Optional improvement (not required): SiC only in one pole (e.g. HV−) and a contactor only in the other pole.
One open SiC switch interrupts the current; the second pole only needs galvanic separation (SAF-002 stage 2).
That halves losses and parts but gives up the redundancy of two fast switches.

### P9 – Short-circuit turn-off ⚠️

Short circuit at the inverter side, loop inductance ≈ 1…3 µH (a few metres of cable): di/dt = 584 V / 3 µH
≈ 200 A/µs (600 A/µs at 1 µH). Detection by the ACS71240 FAULT at 50 A (response 1.5 µs typ) + driver delay
(≈ 0.1 µs) + turn-off (≈ 0.1 µs) ≈ 2 µs → current at turn-off **≈ 400 A** (up to ≈ 1 kA at 1 µH unless the
MOSFET's saturation current limits it first). SAF-004 (10 µs) is met; the issues are:
- the turned-off current must be inside the pulse/short-circuit rating of the SCT020H120G3AG – to be checked
  in its datasheet (I<sub>DM</sub>, short-circuit withstand time);
- the energy stored in the loop inductance (½ L I² ≈ 0.24 J at 3 µH, 400 A) must be absorbed without exceeding
  1200 V → **overvoltage clamp across each pole switch** (TVS string or varistor), new **MHW-070 (P)**;
- faster alternative: gate driver with desaturation detection and soft turn-off (e.g. Infineon EiceDRIVER X3
  Analog family 1ED34xx instead of the X3 Compact 1ED3121), new **MHW-071 (P)** as verification requirement.

### P10 – Pack fuse ⚠️

Prospective short-circuit current: 160 cells × ≈ 0.2 mΩ (350 Ah LFP) ≈ 32 mΩ + ≈ 160 cell connectors
× 0.05 mΩ ≈ 8 mΩ + cables, contactors, fuse ≈ 10 mΩ → ≈ 50 mΩ → 584 V / 50 mΩ ≈ **12 kA**.
Change **(P)** to MHW-028/SAF-005: DC fuse ≥ 600 V DC (preferably 1000 V DC), **breaking capacity ≥ 20 kA DC**,
rated current 32…40 A, battery/semiconductor characteristic (e.g. 14 × 51 mm or NH00 gBat/aR).

### P11 – Precharge ⚠️

The DC-link capacitance on the battery input of the GW8KN-ET is unknown; for 10 kW class inverters
0.2…1 mF is typical → energy in the precharge resistor ½ C V² = **34…170 J** at 584 V. Example 100 Ω: peak
5.8 A / 3.4 kW, τ = 20…100 ms, done within 0.5 s.

Risk: if the inverter input is shorted or the precharge path is stuck, the resistor sees V²/R = 3.4 kW for
the full `precharge_timeout` (5 s → 17 kJ) and burns. Changes **(P)**:
- MHW-026: precharge resistor pulse-rated for ≥ 200 J and thermally protected (PTC precharge resistor or
  thermal fuse);
- new MSW-007: abort the precharge when the inverter voltage has not reached **50 % of the pack voltage
  after 1 s**, and wait **≥ 60 s** between retries (resistor cooling).
- Measure the DC-link capacitance during commissioning (precharge curve) and log it.

### P12 – Contactors at 600 V DC ✅

EV-type HV DC contactors with 12 V coils, 750…1000 V DC, 50…150 A, with auxiliary contacts are widely
available. Two details are added to MHW-025 **(P)**: rated ≥ 750 V DC and ≥ 40 A continuous; able to break
`oc2_level` at 600 V DC in **both** current directions as an emergency (failed-short SiC switch); many HV
contactors are polarised and break much less in the reverse direction.

### P13 – Isolation 600 V and isolated parts (F12) ⚠️

**Where reinforced isolation is needed.** Reinforced (≥ 600 V working voltage) is needed only between HV
circuits and circuits that can be touched or connect to other equipment (master LV domain with USB, CAN, PE,
enclosure). Between HV− and HV+ (both not accessible) basic insulation for 600 V is enough. SAF-013 and
MHW-060 are refined accordingly **(P)**. PCB guide values (IEC 60664-1, pollution degree 2, overvoltage
category II, to be confirmed): reinforced ≈ 6.4 mm creepage, ≈ 5.5 mm clearance; parts crossing a reinforced
barrier need ≥ 8 mm package creepage (wide body).

**Parts of the concept and replacements:**

| Function | Concept part | Rating found | Replacement (verified datasheet values) |
|---|---|---|---|
| Gate driver | 1ED3121MU12H | UL 1577 only, **no VIORM/VIOWM** (not certified reinforced) | **1ED3121MC12H**: same package and pinout, reinforced per IEC 60747-17, VIOWM 1250 Vrms, creepage > 8 mm ([datasheet](https://www.infineon.com/assets/row/public/documents/24/49/infineon-1ed31xxmc12h-1ed-x3-compact-datasheet-en.pdf)); LCSC C17497486 |
| Gate supply | RECOM R05P21509D (+15/−9 V) | **basic** insulation only ([datasheet](https://recom-power.com/pdf/Econoline/RxxP2xxyy.pdf)), wrong voltages (F12) | **Mornsun QA123C-1803R3**: 12 V in (from the 12 V coil rail), **+18/−3 V**, ±100 mA, reinforced, 5 kVAC, partial discharge 1700 V, 3.5 pF ([datasheet](https://www.mornsun-power.com/public/uploads/pdf/QAxx3C-R3.pdf)); LCSC C5369880 (YLPTEC) / C19188322 (EVISUN) – second sources; creepage and working voltage not stated → to be confirmed by the vendor. Fallback with fully documented rating: **TI UCC14141-Q1** (12 V in, VDD/VEE set to +18/−4 V, 1.5 W, reinforced, VIOWM 1414 VDC, creepage > 8 mm, SSOP-36; [datasheet](https://www.ti.com/lit/ds/symlink/ucc14141-q1.pdf); low LCSC stock) |
| CAN isolator | ISOW1044 | reinforced, VIOWM 1500 VDC, creepage > 8 mm ([datasheet](https://www.ti.com/lit/ds/symlink/isow1044.pdf)) | keep (not the ISOW1044**B**, which is basic) |
| Master supply | LM2596HVS from one module | – | **Mornsun PV15-27B12R3**: 100…1000 V DC in, 12 V / 15 W, reinforced, 4000 VAC ([datasheet](https://www.mornsun-power.com/public/uploads/pdf/PV15-27BxxR3.pdf)); external 2 A / 1000 V DC fuse; not on LCSC (hand-assembled) |

Gate drive power: SCT020H120G3AG Q<sub>g</sub> = 121 nC; the switches only switch on connect/disconnect, so the
average gate power is in the mW range; ≥ 1 W modules have ample margin.

Consequence for MHW-003: the PV15-27B12R3 delivers 15 W, not the 20 W proposed. Master 3 W + holding
4 W = 7 W continuous fits; the pull-in of one contactor (≈ 12 W for ≈ 0.1 s) is taken from a buffer capacitor
on the 12 V rail. MHW-003 changed to **≥ 15 W continuous + buffered pull-in (P)**. Its no-load loss has to be
measured against SAF-017 (master ≤ 0.5 W in the low-power state); if it is too high, the master needs a
switch-off of the PV module and a small wake-up supply.

### P14 – Inverter protocol and CAN in MicroPython ⚠️

**Protocol.** Reverse engineering is probably not necessary:

| Option | Evidence |
|---|---|
| **BYD HVS/HVM over CAN** (11-bit IDs, 500 kbit/s; battery sends 0x110 limits every 2 s, 0x150 SOC/SOH, 0x1D0 V/I/T, 0x210 temperatures every 10 s, identification burst 0x250/0x290/0x2D0/0x3D0 on request 0x151) | GoodWe lists BYD HVS/HVM as compatible with ET PLUS+ (16A) ([compatibility overview](https://en.goodwe.com/Ftp/Downloads/User%20Manual/GW_Battery%20Compatibility%20Overview-EMEA_EN.pdf)); the open-source [Battery-Emulator](https://github.com/dalathegreat/Battery-Emulator) uses this protocol for GoodWe ET (wiki: "BYD HVS/HVM over CAN", several user reports, [issue #28](https://github.com/dalathegreat/Battery-Emulator/issues/28)) |
| Native GoodWe HV protocol (0x453…0x460, 250 kbit/s) | One reverse-engineering effort for the EH series ([gw-ev](https://github.com/yasko-pv/gw-ev)); not official |
| GCE RBMS07S70S50A (Hunan GCE) | No public protocol; GCE markets per-brand inverter protocols, so it probably speaks the native GoodWe or a BYD-style protocol to the inverter |

Known pitfalls (user reports): BMS CAN on inverter pins 4/5; the battery voltage must be present at the
inverter terminals before it accepts the battery communication; inverter firmware ARM 17 (449) reportedly
broke third-party CAN; one report of an ET ignoring the CAN current limits (→ SAF-015, the BMS protects itself).

Change **(P)** to COM-001/OPEN-02: implement the **BYD HVS/HVM CAN protocol** first (documented in
open-source code, verifiable without the GCE system); sniffing the GCE system remains the fallback and a
cross-check (bit rate, cycle times, behaviour on faults).

**CAN in MicroPython.** Mainline `machine.CAN` (since v1.28) exists only for STM32/MIMXRT/Alif, **not for ESP32**.
ESP32 support: open PR [#19461](https://github.com/micropython/micropython/pull/19461) (ESP-IDF ≥ 5.4 TWAI
driver, tested on ESP32-S3, `MODE_SILENT` = listen-only) or the user C module
[straga/micropython-esp32-twai](https://github.com/straga/micropython-esp32-twai) (`CAN.LISTEN_ONLY`). Neither
provides a receive timestamp → `time.ticks_us()` in the RX interrupt handler (sufficient for the 1 ms of
MSW-021). The master therefore needs a **custom MicroPython build** (new MSW-024 **(P)**); the playground
`CAN.py` relied on a non-mainline `machine.CAN` as well.

### P15 – HV voltage measurement ✅

600 V across a divider: chain of ≥ 6 resistors (e.g. 1206, ≤ 100 V each, 0.1 %, 25 ppm/K) → ±0.5 % is reached
after calibration with a 16-bit ADC (ADS1118 class). Creepage along the chain is part of P13.

### P16 – Insulation monitoring ✅

At 584 V: `iso_trip` 100 Ω/V = 58 kΩ, `iso_warn` 500 Ω/V = 292 kΩ – both inside the measuring range
10 kΩ…10 MΩ (MHW-040). With the transformerless inverter connected, its Y-capacitors and the grid reference
dominate; the meaningful measurement is in STANDBY before each connection. `iso_en` covers interference (closed OPEN-08).

### P17 – Deep discharge by the BMS itself ❌

After an under-voltage trip the pack is disconnected, but slaves and master keep drawing current: slave
≈ 9 mA (P6, up to 40 mA at 2 W) from each module, master ≈ 3 W from the pack. An LFP cell has only ≈ 1 %
(≈ 3.5 Ah) between 2.5 V and the damage region → at 9…40 mA the cells are damaged after **4…16 days**.

New requirements **(P)**:
- SAF-017: after an under-voltage trip (and in any disconnected state below `cell_uv_warn`) master and slaves
  enter a low-power state: slave **≤ 1 mA** per module, master **≤ 0.5 W** from the pack (incl. the HV DC/DC
  no-load loss), periodic wake-up for measurement (e.g. every 10 min). With 1 mA the 3.5 Ah last ≈ 5 months.
- SAF-018: after an under-voltage trip a user reset shall allow reconnecting **for charging only** (discharge
  limit 0) until all cells are above `cell_uv_warn`.
- Slave: SHW-045 (low-power hardware: converter quiescent current, ESP32-S3 deep sleep), SWS-005 (low-power
  state). Master: MSW-008.

### P18 – Radio through a metal rack ⚠️

A closed steel rack can attenuate 2.4 GHz strongly. Change **(P)** to SHW-051/MHW-053: the layout shall allow
the ESP32-S3-WROOM-1**U** variant (u.FL connector, external antenna) as an assembly option.

---

## 3. Requirement changes from this check

All changes are marked **(P)** in the requirement documents.

| Document | ID | Change |
|---|---|---|
| System | SAF-013 | Reinforced isolation only between HV and accessible circuits; basic for 600 V between HV domains (P13) |
| System | SAF-005 | Fuse breaking capacity ≥ 20 kA (P10) |
| System | COM-001, OPEN-02 | BYD HVS/HVM CAN protocol first, GCE sniffing as fallback (P14) |
| System | EST-001, new `full_charge_interval` | Periodic full charge for SOC re-anchoring (P7) |
| System | new SAF-017, SAF-018 | Low-power state, charge-only recovery (P17) |
| System | `oc2_time` range | 0.5…5 s (P1) |
| System | `espnow_channel` | `auto` default (P3) |
| Master | MHW-001, MHW-003, MHW-022 | PV15-27B12R3, 15 W + buffered pull-in, 1ED3121MC12H + QA123C-1803R3 (P13) |
| Master | MHW-025, MHW-026, MHW-028, MHW-053, MHW-056, MHW-060 | Contactors, precharge resistor, fuse, antenna option, logging, isolation (P2, P10–P13, P18) |
| Master | new MHW-070, MHW-071, MSW-007, MSW-008, MSW-024; MSW-020 | Overvoltage clamp, short-circuit verification, precharge abort, low-power state, CAN firmware; protocol choice |
| Slave | SHW-043, SHW-051, SHW-060, SWS-020, new SHW-045, SWS-005 | Radio always on, antenna option, isolation, encrypted peers, low-power state |

---

## 4. Decisions (2026-11-20)

| # | Decision |
|---|---|
| P1 | Accepted: `oc2_time` 0.5…5 s. |
| P2 | Changed: history limited to **≤ 7 days** of 1-minute data, configurable with `log_days` (0…7, default 7), ≈ 4 MB → ESP32-S3-WROOM-1-N16R8 (MHW-056). |
| P3 | Accepted, plus: `espnow_channel` 1…13 states that the router's 2.4 GHz channel is fixed to this channel (no scanning); `auto` = router may change it. |
| P7 | Accepted with `full_charge_interval` default **0 = off**. The capacity is configurable with `cell_capacity_ah` (10…1000 Ah). |
| P9 | Gate driver with DESAT and soft turn-off from the **EiceDRIVER X3 Digital** family (1ED38xx, I²C), if the GPIO budget allows (MHW-071, master architecture). |
| P10 | Accepted, fuse rated **1000 V DC**. |
| P11, P13, P14, P17 | Accepted. |
| P18 | **Not accepted**: on-module PCB antenna only. |
| P4, P12 | Not decided yet (SWS-020 encrypted peers, MHW-025 contactor ratings remain (P)). |
