# Master concept review – hw/master/CALU_BMS_MASTER.epro2 (V1.4.1.0)

| | |
|---|---|
| Status | Review 0.4 |
| Source | schematic pages MAIN, CAN, RELAY, POWER and the PCB netlist of the EasyEDA project |
| Checked against | [System requirements](requirements.md) 0.7, [Master requirements](master_requirements.md) 0.4 |

## 1. Concept summary

| Block | Implementation in V1.4.1.0 |
|---|---|
| MCU | ESP32-S3-WROOM-1-N8R8, USB-C, UART header, reset/boot, 2 LEDs, buzzer, GPIO header |
| Supply | from B16+ of one module: LM2596HVS-5.0 (60 V) → +5 V, AMS1117-3.3 → 3.3 V |
| Stage 1 disconnect | per pole two SCT040H120G3AG SiC MOSFETs back-to-back (bidirectional): TOP between BAT+/INV+, BOT between BAT−/INV−; isolated gate drivers 1ED3121, one isolated supply R05P21509D (+15/−9 V) |
| Stage 2 disconnect | ULN2003 → 4 outputs: REL_SAFE, REL_EXT0 (connectors for external relays), REL_INT0/1 (on-board G5Q-14 signal relays with dry contacts) |
| Fault path | ACS71240 FAULT# NAND MCU BAT_FAULT → REL_SAFE |
| Pack measurement | dividers 4 × 620 kΩ / 10 kΩ for BAT+, BAT−, INV+, INV− → ADS1118 (2 differential channels), referenced to master GND |
| Current | ACS71240LLCBTR-030B3 (Hall, 30 A) between the two TOP MOSFETs |
| CAN | ISOW1044 (isolated, integrated DC/DC) and SN65HVD230 (non-isolated) on the same bus/TX/RX, RJ45, 120 Ω, PESD1CAN |
| Temperature | DS18B20 on board |

The basic idea is sound and feasible: ESP32-S3 master, bidirectional SiC stage for fast disconnection,
relays for galvanic separation, isolated gate drivers, isolated CAN. The findings below must be fixed
before the concept meets the system requirements.

## 2. Findings

Severity: **C** = critical (damage/safety), **M** = major (requirement not met), **m** = minor.

| # | Sev | Finding | Fix (→ requirement) |
|---|---|---|---|
| F1 | C | **Pack short circuit through the gate-drive ground.** The Kelvin-source pins (pad 2) of all four SiC MOSFETs are on the same net `GND_ISO`. This ties the TOP source node (≈ BAT+) to the BOT source node (≈ BAT−). As soon as TOP and BOT are switched on, the full pack is shorted through the Kelvin pins and the isolated supply. | One isolated gate supply and driver ground per pole, isolated from each other for the full pack voltage (MHW-022). |
| F2 | C | **Measurement only works with the master on the bottom module.** The BAT±/INV± dividers and the ADS1118 are referenced to master GND. With the master on any other module, BAT− is several hundred volts below master GND; the ADS1118 inputs (allowed GND…VDD) would be driven far negative. The dividers also connect master GND to both pack ends (no isolation). | HV measurement in an isolated domain referenced to pack negative (MHW-030, MHW-031). |
| F3 | M | **Current sensor placement.** With the 25 A rating the Hall sensor ACS71240 (±30 A) is kept. But it sits in the HV+ path and its output is referenced to master GND: the SOIC-8 isolation is only 297 Vrms / 420 V peak *basic*, less than the up to 600 V between pack and master GND, and not reinforced. Its FAULT trip is fixed at 1 × range (30 A for the 030B3), too close to the 25 A operating current. Offset (±15 mV ≈ ±0.34 A max, ±28 mV with lifetime drift) needs automatic zeroing. | Sensor in the HV− path, supplied and read in the HV− domain (functional isolation only), auto-zero while disconnected; variant **ACS71240LLCBTR-050B3** (same SOIC-8 footprint, ±50 A, FAULT at 50 A) (MHW-032, MHW-024). |
| F4 | M | **CAN isolation is bypassed.** PESD1CAN (pad 3) and the RJ45 shield are connected to master GND, but CAN_H/L belong to the isolated side of the ISOW1044. The non-isolated SN65HVD230 sits on the same CAN_H/L and TWAI_TX/RX nets (output conflict on RX if both are fitted). | Only the isolated transceiver; ESD diode to `GND_CAN`; shield via RC to `GND_CAN` or open (MHW-050). |
| F5 | M | **Hardware fault path ends at a relay.** The current-sensor FAULT# and BAT_FAULT only switch REL_SAFE (milliseconds). D_TOP/D_BOT come from the MCU only, so a short circuit is not interrupted within 10 µs independent of firmware (SAF-004). | Hardware over-current latch that disables both gate drivers directly (MHW-024). |
| F6 | M | **Conduction losses.** Each pole has two SCT040H120G3AG in series (40 mΩ typ at 25 °C, 72 mΩ at 175 °C, V<sub>GS</sub> = 18 V) → per pole 50 W at 25 A and 25 °C, up to 90 W hot; both poles 100…180 W at full current (≈ 8…14 W per pole at 10 A). | Heatsinks on the SiC switches (MHW-020); lower-R<sub>DS(on)</sub> part in the same package, e.g. SCT020H120G3AG: 23…46 W per pole (MOPEN-01). |
| F7 | m | **Pack current through the PCB** (BAT/INV connectors JL136HT, SiC, sensor): 25 A is possible on the PCB with wide pours / 2 oz copper; the connector rating must be checked. | Power path rating (MHW-020). |
| F8 | M | **No precharge circuit, no contactor feedback, no insulation monitoring, no PE connection.** | MHW-026, MHW-027, MHW-040. |
| F9 | m | **Supply LM2596HVS (60 V max)** from B16+ of one module at 58.4 V (16S full): no margin for transients, and the master load unbalances that module. | Supply from the whole pack through an isolated HV DC/DC (150…600 V input); the LV domain then floats and the master can sit anywhere (MHW-001, HW-005). |
| F10 | m | **Contactor coils.** The ULN2003 outputs switch +5 V relays; the external HV contactors need 12 V and more current, and the outputs have no defined state check. | 12 V coil supply on the master from the HV DC/DC, drivers with economizer, fail-safe off, feedback (MHW-025, MHW-027). |
| F11 | m | **Gate-driver inputs at reset:** D_TOP/D_BOT only have an LED + 390 Ω to GND, no defined pull-down while the ESP32 boots. | Explicit pull-downs, driver enable only after MCU init (MHW-023). |
| F12 | m | **Gate voltage and supply isolation.** The R05P21509D gives +15 V/−9 V and has only **basic** insulation. The ST G3 MOSFETs are specified at +18 V (SCT040: 49 mΩ instead of 40 mΩ at 15 V), recommended off level −5…0 V; −9 V is inside the absolute maximum (−10 V) but without margin. | Mornsun QA123C-1803R3 (+18/−3 V, reinforced) or TI UCC14141-Q1 (MHW-022, plausibility check P13). |
| F13 | M | **Gate driver isolation not certified reinforced.** The 1ED3121MU12H datasheet gives only UL 1577 (5.7 kVrms), no VIORM/VIOWM. | Pin-compatible 1ED3121MC12H, reinforced per IEC 60747-17, VIOWM 1250 Vrms (MHW-022). |

## 3. Result

Feasible with the fixes above. F1 and F2 change the isolation architecture of the board (section 3 of the
master requirements). With the current rating reduced to 25 A (review 0.2) the Hall sensor stays, F7 is minor,
and F6 is solved with heatsinks.
