# CALU BMS – Master Architecture

| | |
|---|---|
| Status | Draft 0.1 |
| Based on | [Master requirements](master_requirements.md) 0.5, [System architecture](system_architecture.md) 0.1, [Concept review](master_concept_review.md) |
| Hardware basis | concept V1.4.1.0 (`hw/master/CALU_BMS_MASTER.epro2`) with the fixes F1…F13 → **master 2.0** |

Column **Verified**: ✔ = ratings checked against the datasheet during the plausibility check / architecture
work; ○ = typical choice, to be checked during the schematic design (rating, LCSC stock).

---

## 1. Hardware

### 1.1 Block diagram

```
                     ┌──────────────────────────── LV domain (floating, reinforced to all HV) ─────────────────────────────┐
 BAT+ ─F2 2A─► PV15-27B12R3 ─► 12 V ─┬─ buffer 2×2200 µF ─┬─ 4 × low-side coil driver (PWM economizer) ─► K1 K2 K3 K4 coils
 BAT− ────────►  (HV DC/DC)          │                     ├─ QA123C-1803R3 ─╫─► +18/−3 V TOP driver supply (HV+ domain)
                                     │                     ├─ QA123C-1803R3 ─╫─► +18/−3 V BOT driver supply (HV− gate domain)
                                     └─ buck → 3.3 V ── ESP32-S3-WROOM-1-N16R8 ── USB-C (bench supply, flashing)
                                                         │  I²C: RTC RV-3028, TCA9535 expander (LEDs, aux contacts), 2 × 1ED3860MC12M (config)
                                                         │  IN/RDYC ×2, FLT_N (wired-AND) ──╫── 1ED3860MC12M TOP ─► 2 × SCT020H120G3AG (HV+ pole)
                                                         │                                  ╫── 1ED3860MC12M BOT ─► 2 × SCT020H120G3AG (HV− pole)
                                                         │  SPI + DRDY + IMD + OC_FAULT ─────╫── ISOW7741 (power + SPI) / ISO7742 ─► HV− measurement domain
                                                         │  TWAI TX/RX ──────────────────────╫── ISOW1044 ─► CAN (RJ45 pins 4/5)
                                                         └  NTC heatsink ×2, board NTC, buzzer, LEDs
                     └──────────────────────────────────────────────────────────────────────────────────────────────────┘
 HV− measurement domain (reference BAT−):
   ACS71240LLCBTR-050B3 (in BAT− path) ─┐
   U_BAT divider (BAT+ after F1) ───────┼─► ADS131M04 (4 ch, simultaneous, 24 bit) ─► SPI via ISOW7741
   U_INV divider (INV+ − INV−) ─────────┤
   IMD bridge (BAT± → PE, 2 PhotoMOS) ──┘        ACS71240 FAULT (50 A) ─► ISO7742 ─► FLT_N of both drivers
```

### 1.2 Components

| Block | Part | Requirement | Verified | Note |
|---|---|---|---|---|
| MCU | ESP32-S3-WROOM-1-N16R8 (on-module antenna) | HW-001, MHW-053, MHW-056 | ✔ | 16 MB flash: firmware in two OTA slots + ≈ 2 MB history; GPIO35…37 used by octal PSRAM |
| HV supply | Mornsun PV15-27B12R3 (100…1000 V DC → 12 V / 15 W, reinforced) + F2 2 A 1000 V DC | MHW-001…003 | ✔ | off-board or THT; not in the LCSC library |
| 12 V buffer | 2 × 2200 µF / 25 V low-ESR | MHW-003 | ○ | contactor pull-in peaks |
| 3.3 V | synchronous buck 12 V → 3.3 V, ≥ 1 A (e.g. TPS62933) + USB-VBUS OR-ing | MHW-004 | ○ | USB-only bench mode |
| SiC switches | 4 × ST SCT020H120G3AG (H²PAK-7), common heatsink (PE) via insulating pad | MHW-020 | ✔ | heatsink ≈ 0.4 K/W (plausibility P8) |
| Gate drivers | 2 × Infineon 1ED3860MC12M (X3 Digital, reinforced, DESAT, soft-off, I²C) | MHW-022, MHW-071 | ✔ | LCSC C17558509 – thin stock, order early; alternative 1ED3890MC12M |
| DESAT network | 1200 V fast diode + R<sub>DESAT</sub> to the discharge-forward MOSFET of each pole | MHW-071 | ○ | threshold/blanking per MSW-009 |
| Gate supplies | 2 × Mornsun QA123C-1803R3 (12 V → +18/−3 V, reinforced) | MHW-022 | ✔ (creepage to confirm) | fallback TI UCC14141-Q1 |
| Overvoltage clamp | TVS string across each pole switch, ≥ 0.5 J, clamp < 1200 V | MHW-070 | ○ | |
| Current sensor | Allegro ACS71240LLCBTR-050B3 (±50 A, FAULT 50 A) in BAT− path | MHW-032, MHW-024 | ✔ | HV− domain, auto-zero |
| HV ADC | TI ADS131M04 (4 ch simultaneous ΔΣ, 24 bit, SPI) | MHW-031…033 | ○ | ch0 current, ch1 U_BAT, ch2 U_INV, ch3 IMD |
| HV dividers | ≥ 6 × 1206 thin-film 0.1 % 25 ppm/K per divider | MHW-031 | ○ | creepage along the chain |
| HV− isolation | TI ISOW7741 (4 ch 3/1 + integrated isolated power, reinforced) + ISO7742 (2/2) | MHW-030, SAF-013 | ○ | ISOW7741: SCLK, MOSI, CS → / MISO ←; ISO7742: IMD_P, IMD_N → / DRDY, OC_FAULT ← |
| Insulation monitoring | switched resistor bridge: 2 × HV resistor chain (≈ 2 MΩ) BAT+/BAT− → PE via HV PhotoMOS (≥ 1000 V), PE sense via divider into ADS131M04 ch3 | MHW-040, MHW-041 | ○ | ≤ 0.3 mA injection at 600 V |
| Contactor drivers | 4 × N-MOSFET low side (e.g. AO3400A) + diode + 24 V TVS (fast release), gate pull-down | MHW-025 | ○ | LEDC PWM economizer (100 ms pull-in, then hold) |
| Contactor feedback | aux contacts → TCA9535 inputs (RC filtered) | MHW-027 | ○ | |
| Fuse supervision | U_BAT (after F1) vs. sum of module voltages | MHW-028 | – | no extra hardware |
| CAN | TI ISOW1044 (reinforced, integrated power), PESD2CAN to GND_CAN, 120 Ω via jumper, RJ45 (CAN_H pin 4, CAN_L pin 5) | MHW-050…052 | ✔ | listen-only via TWAI mode |
| RTC | Micro Crystal RV-3028-C7 (I²C) + backup capacitor | MHW-055 | ○ | |
| I/O expander | TI TCA9535 (16 I/O, I²C, INT) | – | ○ | LEDs, aux inputs, user button |
| Temperatures | 2 × NTC 10 k on the heatsink (PE side), 1 × board NTC → ESP32 ADC1 | MHW-021 | ○ | `t_switch_max` |
| UI | LEDs (run, fault, K1, K2, K3), buzzer, reset/boot/user buttons, USB-C | MHW-054 | ○ | |
| HV terminals | BAT+, BAT−, INV+, INV−, PE: ≥ 1000 V, ≥ 40 A (bolt or PCB power terminals) | MHW-020 | ○ | |
| Contactor connector | 12-pin: 4 × coil ±, 3 × aux contact, spare | MHW-025, MHW-027 | ○ | |

### 1.3 Isolation domains (from the master requirements, section 2)

| Barrier | Parts crossing it | Rating |
|---|---|---|
| HV (pack) → LV | PV15-27B12R3 | reinforced |
| LV → HV− measurement | ISOW7741, ISO7742 | reinforced |
| LV → HV+ gate / HV− gate | 1ED3860MC12M, QA123C-1803R3 | reinforced |
| LV → CAN | ISOW1044 | reinforced |
| HV− measurement → PE | IMD resistor chains (high-ohmic by design) | resistor chains rated for reinforced (2 × full voltage) |
| HV+ ↔ HV− | gate domains, dividers | basic for 600 V |

### 1.4 GPIO budget (ESP32-S3-WROOM-1-N16R8)

| GPIO | Function | GPIO | Function |
|---|---|---|---|
| IO0 | BOOT button (strap) | IO17 | I²C SDA (RTC, expander, gate drivers) |
| IO1 | NTC heatsink 1 (ADC1) | IO18 | I²C SCL |
| IO2 | NTC heatsink 2 (ADC1) | IO19, IO20 | USB D−/D+ |
| IO4 | NTC board (ADC1) | IO21 | CAN TX |
| IO5 | SPI SCLK → HV− | IO38 | CAN RX |
| IO6 | SPI MOSI → HV− | IO39 | K1 coil PWM (HV+ main) |
| IO7 | SPI MISO ← HV− | IO40 | K2 coil PWM (HV− main) |
| IO8 | SPI CS → HV− | IO41 | K3 coil PWM (precharge) |
| IO9 | ADC DRDY ← HV− | IO42 | K4 coil PWM (spare) |
| IO10 | IMD switch P → HV− | IO43, IO44 | UART0 (console/test) |
| IO11 | IMD switch N → HV− | IO45 | buzzer (strap, pull-down) |
| IO12 | gate IN TOP | IO47 | expander INT |
| IO13 | gate IN BOT | IO3, IO46, IO48 | spare (IO3/IO46 strapping) |
| IO14 | gate RDYC TOP | | |
| IO15 | gate RDYC BOT | | |
| IO16 | FLT_N (wired-AND: both drivers + OC_FAULT) | | |

29 of ≈ 33 usable GPIOs are assigned; slow signals (LEDs, aux contacts, user button) are on the TCA9535.
The X3 Digital drivers fit because they share the I²C bus and the fault line.

## 2. Software

### 2.1 Structure

```
firmware/master/
├─ main.py             safe outputs first (MSW-002), gate-driver bring-up (MSW-009), self test, start tasks
├─ hal/                ads131m04.py · x3digital.py (1ED3860 address/config/status) · contactors.py (PWM economizer, aux)
│                      tca9535.py · rv3028.py · ntc.py · can_twai.py (custom MicroPython CAN module) · imd.py
├─ core/               states.py (INIT/STANDBY/PRECHARGE/CONNECTED/DERATED/FAULT/SERVICE/SNIFF/LOW_POWER)
│                      sequencer.py (connect/disconnect MSW-004, precharge abort MSW-007)
│                      protection.py (SAF-007…010, 016, 017) · limits.py (EST-004, taper) · soc.py (EST-001…003)
│                      balancing.py (BAL-005 target, commands) · insulation.py (bridge calculation)
├─ comm/               slaves.py (ESP-NOW server, pairing, time base, channel) · inverter/byd_hvs.py · inverter/gce.py
│                      sniffer.py (listen-only log, replay) · mqtt_ha.py (discovery, writable config) · web/ (microdot)
├─ app/                config_store.py (schema from common/, S-parameter rules, change log) · history.py (log_days)
│                      faultlog.py · ota.py (master + relayed slave updates)
└─ uses firmware/common/ (protocol, config schema, crc)
```

### 2.2 Run-time behaviour

| Task (asyncio) | Period / trigger | Work |
|---|---|---|
| Measurement | ADS131M04 DRDY (e.g. 250 SPS), processed every 100 ms | current integration without gaps, U_BAT, U_INV, auto-zero when disconnected |
| Protection | 100 ms | all limits, slave timeouts, sensor plausibility, fuse supervision; acts via the sequencer |
| Sequencer | event-driven | connect/disconnect/precharge state machine, contactor feedback |
| Slave link | event-driven + 1 s trigger | time base, data collection, balancing commands, configuration distribution |
| Inverter | protocol cycle (BYD: 2 s / 10 s frames) | send limits/SOC/values, watch `inverter_timeout` |
| Insulation | `iso_period` | switch bridge, wait for settling, compute R<sub>iso+</sub>/R<sub>iso−</sub> |
| SOC/limits | 1 s | SOC, SOH, current/voltage limits, full-charge request |
| MQTT / web | `mqtt_period` / on request | publish, apply validated configuration changes |
| History | 60 s | 1-minute record: pack values + per-module summaries (≈ 130 B) to a LittleFS ring buffer (`log_days`); full cell data (≈ 400 B) to a separate 24 h ring buffer |
| Watchdog | 250 ms | feed only if protection and measurement tasks ran |

Garbage collection is triggered explicitly once per 100 ms cycle (plausibility P1).

### 2.3 Firmware build

The master needs a **custom MicroPython build** (MSW-024): ESP-IDF ≥ 5.4 with the ESP32 `machine.CAN` port
(micropython/micropython#19461) or the user C module `micropython-esp32-twai`, and the application frozen
into the firmware. The build runs in a container (ESP-IDF image), later
in GitHub Actions; the same build (without CAN) is used for the slaves.
