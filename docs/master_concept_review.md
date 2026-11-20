# Master concept review – hw/master/CALU_BMS_MASTER.epro2 (V1.4.1.0)

| | |
|---|---|
| Status | Review 0.1 |
| Source | schematic pages MAIN, CAN, RELAY, POWER and the PCB netlist of the EasyEDA project |
| Checked against | [System requirements](requirements.md) 0.4, [Master requirements](master_requirements.md) 0.1 |

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
| F3 | M | **Current sensor.** ACS71240: 30 A range (100 A required), SOIC-8 isolation 297 Vrms *basic* (≈ 420 V peak) < 467 V pack and not reinforced; Hall-sensor offset/drift is unlikely to reach < 50 mA (MEA-004). | Shunt in the HV− path read by an isolated ΔΣ ADC in the pack-negative domain, plus hardware over-current comparator (MHW-032, MHW-024). |
| F4 | M | **CAN isolation is bypassed.** PESD1CAN (pad 3) and the RJ45 shield are connected to master GND, but CAN_H/L belong to the isolated side of the ISOW1044. The non-isolated SN65HVD230 sits on the same CAN_H/L and TWAI_TX/RX nets (output conflict on RX if both are fitted). | Only the isolated transceiver; ESD diode to `GND_CAN`; shield via RC to `GND_CAN` or open (MHW-050). |
| F5 | M | **Hardware fault path ends at a relay.** The current-sensor FAULT# and BAT_FAULT only switch REL_SAFE (milliseconds). D_TOP/D_BOT come from the MCU only, so a short circuit is not interrupted within 10 µs independent of firmware (SAF-004). | Hardware over-current latch that disables both gate drivers directly (MHW-024). |
| F6 | M | **Conduction losses.** Each pole has two SiC MOSFETs in series (≈ 2 × 40 mΩ class) → per pole 50 W at 25 A, 800 W at 100 A; both poles double that. Not feasible on a PCB at 100 A; already needs heatsinks at the GW8K-ET's ~25 A. | Parallel devices on a heatsink, or a hybrid switch (contactor carries the current, SiC only commutates); decided in the plausibility check (MHW-020, OPEN-07). |
| F7 | M | **Pack current through the PCB** (BAT/INV connectors JL136HT, SiC, sensor): 100 A needs bus bars/heavy copper; the connector rating must be checked. | Power path rating (MHW-020). |
| F8 | M | **No precharge circuit, no contactor feedback, no insulation monitoring, no PE connection.** | MHW-026, MHW-027, MHW-040. |
| F9 | m | **Supply LM2596HVS (60 V max)** at 58.4 V (16S full) – no margin for transients. | 100 V-rated supply (MHW-001). |
| F10 | m | **Contactor coils.** The ULN2003 outputs switch +5 V relays; external HV contactors usually need 12/24 V and more current, and the outputs have no defined state check. | Contactor drivers with own coil supply, fail-safe off, feedback (MHW-025, MHW-027). |
| F11 | m | **Gate-driver inputs at reset:** D_TOP/D_BOT only have an LED + 390 Ω to GND, no defined pull-down while the ESP32 boots. | Explicit pull-downs, driver enable only after MCU init (MHW-023). |

## 3. Result

Feasible with the fixes above. F1 and F2 change the isolation architecture of the board (section 3 of the
master requirements); F6/F7 are the main questions for the 100 A target and go into the plausibility check.
