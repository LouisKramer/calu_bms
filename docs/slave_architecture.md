# CALU BMS – Slave Architecture

| | |
|---|---|
| Status | Draft 0.1 |
| Based on | [Slave requirements](slave_requirements.md) 0.5, [System architecture](system_architecture.md) 0.1 |
| Hardware basis | slave 3.0.0.0 design (branch `slave-hw-3.0.0.0`, `hw/CALU_BMS_Slave_3_0_0_0_schematic.md`), updated to the current requirements → **slave 4.0** |

---

## 1. Hardware

### 1.1 Block diagram

```
 cell taps T0…T16 ──┬── 1 kΩ per tap ── 17 × PhotoMOS (AQY280S) ── BUS_A / BUS_B ── transfer H-bridge (4 × AQY280S)
 (module 16S)       │                                                                    │
                    │                                                     C_FC 1 µF PP film (flying capacitor)
                    │                                                                    │
                    │                                         OPA333 buffer ── ADS1220 (24 bit) ── REF5040 (4.096 V)
                    │                                                                    │ AIN2: module voltage divider
                    │                                                                    │ AIN3: NTC at bleed resistors
                    ├── fuse/PTC per tap ── 16 × balancing PhotoMOS (AQY282GS) ── 2 × 33 Ω 2512 per cell (≈ 200 mA)
                    │                                       ▲ PCA9685 (I²C, OE = off at reset)
                    │
 module + / − ──────┴── LM5164 (100 V buck) → 5 V ─┬─ TLV75733 → 3.3 V ── ESP32-S3-WROOM-1-N8R8 (PCB antenna)
                                                    └─ load switch → 5VA (analog, off in low-power state)

 ESP32-S3: SPI → ADS1220 · I²C → PCA9685 · 1-Wire → 4 × DS18B20 · 4-bit address DIP · 2 LEDs · USB-C
           · active balancer connector (GND, 3.3 V, EN, PWM)
```

### 1.2 Components

| Block | Part | Requirement | Note |
|---|---|---|---|
| MCU | ESP32-S3-WROOM-1-N8R8, on-module PCB antenna | SHW-050, SHW-051 | 8 MB flash is enough (no long-term logging on the slave) |
| Supply | LM5164DDA 100 V buck → 5 V; TLV75733 → 3.3 V; load switch (e.g. TPS22917) for the analog 5VA rail | SHW-040…045 | EN/UVLO ≈ 9 V (4 cells); low quiescent current for SHW-045 |
| Tap multiplexer | 21 × AQY280S PhotoMOS (350 V, SO-4), 74HCT154 + 74HCT138 decoders | SHW-001, SHW-006 | only the two taps of one cell can be on |
| Flying capacitor | 1 µF polypropylene film (MKP), ≥ 63 V | SHW-002 | no X7R (dielectric absorption) |
| ADC + reference | ADS1220IPW (24 bit, 330 SPS, PGA bypassed) + REF5040 (A grade preferred) + OPA333 buffer | SHW-002…005 | error budget ≈ 1.2 mV (plausibility P5) |
| Module voltage | divider top tap → ADS1220 AIN2 | SHW-007 | plausibility vs. cell sum (`plaus_tol`) |
| Balancing | 16 × AQY282GS (60 V, 0.8 A) + 2 × 33 Ω 2512 per cell, driven by PCA9685PW | SHW-020…024 | ≈ 200 mA at 3.3 V; all off with OE (pull-up) |
| Tap protection | fuse or PTC per tap in the balancing path; 1 kΩ in the measurement path | SHW-008 | **to add** compared with 3.0 |
| Temperatures | 4 × DS18B20 (1-Wire) on cells/bus bars; NTC at the bleed resistors (AIN3); ADS1220 die temperature | SHW-010…012 | |
| Active balancer | JST-XH 4-pin: GND, +3.3 V (≤ 50 mA), EN, PWM (100 kΩ pull-downs) | SHW-030…033 | power current not through the slave |
| Address | 4-bit DIP switch (0…15) | SHW-052 | |
| UI / service | 2 LEDs, reset + boot buttons, USB-C (native USB, ESD protected) | SHW-053, SHW-054 | USB GND = module negative → only via ≥ 1 kV isolator with cells connected |

### 1.3 Changes from slave 3.0.0.0

| Change | Reason |
|---|---|
| Load switch for the analog 5VA rail; PCA9685 and DS18B20 supply switchable | low-power state ≤ 1 mA (SHW-045, SAF-017) |
| Fuse/PTC per tap in the balancing path | SHW-008 |
| Active balancer connector 4-pin (as already changed on the 3.0 branch) | SHW-030 |
| Mounting holes and board edge keep reinforced distances for 600 V to the enclosure | SHW-060, SHW-061 |
| Address DIP 4-bit covers 10 modules | SHW-052 |

### 1.4 GPIO budget (ESP32-S3-WROOM-1-N8R8)

| Function | GPIOs | Pins |
|---|---|---|
| Cell select (74HCT154 A0…A3, enable) | 5 | IO4…IO8 |
| Transfer select (XFER_n, POL, DISCH) | 3 | IO15…IO17 |
| SPI ADS1220 (CS, DIN, SCLK, DOUT, DRDY) | 5 | IO10…IO14 |
| I²C PCA9685 (SDA, SCL), balancing OE | 3 | IO1, IO2, IO18 |
| 1-Wire | 1 | IO9 |
| Active balancer EN, PWM | 2 | IO21, IO38 |
| LEDs | 2 | IO39, IO40 |
| Address DIP | 4 | IO41, IO42, IO47, IO48 |
| Analog rail enable (new) | 1 | IO3 (strapping pin, pulled down = off) |
| USB D−/D+ | 2 | IO19, IO20 |
| **Total** | **28** of ≈ 33 | spare: IO45, IO46 (strapping), UART0 TX/RX for test |

## 2. Software

### 2.1 Structure

```
firmware/slave/
├─ main.py            start-up: safe outputs first (SWS-001), self test, state machine, watchdog
├─ hal/               ads1220.py · mux.py (tap/transfer sequencing) · pca9685.py · ds18b20.py · addr.py · power.py
├─ measurement/       scan.py (one module scan) · calib.py (gain/offset per channel) · plaus.py (open tap, sum check)
├─ balancing/         executor.py (apply master command, local safety stops, pause during scan) · active.py
├─ link/              espnow_client.py (pairing, channel scan, MAC filter) · timesync.py
├─ app/               states.py (INIT/SEARCH/CONFIG/RUN/FAULT/LOW_POWER) · config_store.py · faultlog.py · console.py · ota.py
└─ uses firmware/common/ (protocol, config schema, crc)
```

### 2.2 Run-time behaviour

| Task (asyncio) | Period / trigger | Work |
|---|---|---|
| Scan | trigger from master (time base), every `meas_period` | balancing off → 16 cells: charge C_FC, transfer, settle, convert (≈ 20 ms/cell → ≈ 0.35 s) → module voltage, NTC → balancing on again |
| Evaluate | after each scan | calibration, plausibility, local limits; events to master within 200 ms |
| Report | after each scan | data message to master (≈ 100 B) |
| Temperatures | every 2 s | DS18B20 conversion (750 ms, non-blocking) |
| Link | event-driven | receive commands, config, time sync; channel scan when the master is lost |
| Balancing watchdog | 1 s | stop balancing after `slave_bal_timeout` without command |
| Low power | on command or timeout | everything off, deep sleep, wake every 10 min, scan, report, sleep |

States: INIT → SEARCH → CONFIG → RUN, plus FAULT and LOW_POWER (SWS-003, SWS-005). Balancing only in RUN.

### 2.3 Calibration and test

- Calibration (SWS-042): apply a reference voltage to all cell inputs (precision source + 6½-digit DMM),
  store gain/offset per channel and the REF5040/ADC die temperature at calibration on the slave.
- Production test (SWS-070): script over USB console – supply rails, every mux channel against a reference
  divider, every balancing channel alone (current via the module supply), DS18B20 count, address switch, LEDs,
  active balancer outputs.
