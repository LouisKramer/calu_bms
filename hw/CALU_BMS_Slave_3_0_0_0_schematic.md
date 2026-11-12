# CALU BMS Slave 3.0.0.0 – Schematic specification

Flying-capacitor cell measurement, no cell-monitor IC. Design inputs:

| Item | Value |
|---|---|
| Cells per slave | 4..16 in series (LFP, 2.5–3.65 V/cell), unused taps bridged to the top tap |
| String voltage | 10–58.4 V, design rating 100 V |
| Supply | from its own string (B+ / B−), 100 V buck |
| Measurement | 1 flying capacitor, PhotoMOS multiplexer, zero-drift buffer, ADS1220 24 bit + REF5040 |
| Balancing | passive, ~200 mA/cell (2x 33 Ω 2512 in parallel), PCA9685 → PhotoMOS |
| MCU / comms | ESP32-S3-WROOM-1-N8R8, ESP-NOW (wireless = galvanic isolation to the master) |
| Other | 4x DS18B20, 4-bit address DIP, 2 LEDs, USB-C (programming), 20-pin active balancer header (pin-compatible with 2.0.1.0 U18) |

Net naming: `T0..T16` = cell taps at the connector (`T0` = B−, `Tn` = + of cell n).
`Tn_F` = after the tap fuse. `GND` = board ground, comes **only** from the power connector (B−).
`T0` is not connected to GND on the board: the flying capacitor measures each cell floating, and the
supply current must not flow through the T0 sense wire.

> **Source of truth is now the SKiDL design in `hw/slave_3_0/`** (generated KiCad project in
> `hw/slave_3_0/kicad/`, `make sch` / `make pcb`). Reference designators there use one hundred block per
> sheet (R1xx power, 2xx MCU, 3xx cells, 4xx meas_mux, 5xx ADC, 6xx balancing) and differ from the
> short names in this document.

---

## 0. Block diagram

```
           J1 (cell taps T0..T16)                    J2 (power B+/B-)
                 │                                          │
        ┌────────┴─────────┐                         F1, D1, TVS
        │ per tap: fuse    │                                │
        └──┬───────────┬───┘                          LM5164 100V buck → +5V ──► TLV75733 → +3V3
           │           │                                   │            └► ferrite → +5VA (analog)
   BALANCING (sheet 6) │ MEAS_MUX (sheet 4)
   16x PhotoMOS +      │   1k per tap ─► 17x PhotoMOS ─► BUS_A (even taps) / BUS_B (odd taps)
   2x33R per cell      │                 driven by 74HCT154 + BAT54A diode-OR (hardware: only
   driven by PCA9685   │                 the 2 taps of ONE cell can be on)
   OE pulled high      │                         │
   = off at reset      │                 C_FC 1µF PP film between BUS_A and BUS_B
                       │                         │
                       │                 4x PhotoMOS transfer H-bridge (74HCT138, only when
                       │                 all tap switches are off) ─► FC_HI / GND
                       │                         │
                       │                 ADC (sheet 5): 10k ─► OPA333 buffer ─► ADS1220 AIN0
                       │                 AIN2 = string divider, AIN3 = NTC at bleed resistors
                       │                         │ SPI
                       └──────────────────► ESP32-S3 (sheet 2) ◄── I2C ── PCA9685
```

---

## 1. Sheet POWER

```
J2.1 (B+) ─ F1 0.5A ─ D1 (Schottky 100V 1A, reverse polarity) ─┬─ VIN_HV
J2.2 (B−) ─ GND (power return, separate wire from T0)          │
                                                     D2 SMBJ60A ┤ (cathode VIN_HV, anode GND)
                                       C1 22µF/100V electrolytic┤
                                       C2,C3 2.2µF/100V X7R 1210┤
                                                                └─ U2 LM5164 VIN
```

| Part | Pin | Net / component |
|---|---|---|
| U2 LM5164DDA (HSOIC-8) | VIN | VIN_HV, plus C4 100 nF/100 V 0603 directly at the pin |
| | GND, PAD | GND (thermal vias under PAD) |
| | EN/UVLO | divider VIN_HV – R1 – EN – R2 – GND, set turn-on ≈ 9 V (works down to 4 cells) |
| | RON | R3 to GND, sets switching frequency (≈ 300–400 kHz) |
| | BST | C5 2.2 nF to SW |
| | SW | L1 → +5V |
| | FB | R4 316 kΩ 1 % from +5V, R5 100 kΩ 1 % to GND → 1.2 V × (1 + 316/100) = 4.99 V |
| | PGOOD | nc (or test pad) |
| L1 | | 47–100 µH, ≥ 1 A saturation (from WEBENCH) |
| C6, C7 | | 2x 22 µF/10 V X7R on +5V |
| D3 | | USB VBUS → Schottky (e.g. PMEG6020) → +5V (USB-only power for flashing) |
| U3 TLV75733PDBV | IN, EN | +5V (+ 1 µF) |
| | OUT | +3V3 (+ 10 µF + 100 nF) |
| | GND | GND |
| FB1 | | ferrite bead 600 Ω @ 100 MHz: +5V → +5VA, + 10 µF + 100 nF on +5VA |

R1/R2/R3/L1: calculate with TI WEBENCH (input 10–60 V, 5 V/0.6 A). The string supplies ~0.5 W on average,
equal for all cells (fixes the uneven load of 2.0.1.0).

---

## 2. Sheet MCU (ESP32-S3-WROOM-1-N8R8)

| GPIO | Module pin | Net | Notes |
|---|---|---|---|
| EN | 3 | EN | 10 kΩ to +3V3, 1 µF to GND, reset button to GND |
| IO0 | 27 | BOOT | 10 kΩ to +3V3, boot button to GND |
| IO1 | 39 | I2C_SDA | 4.7 kΩ to +3V3 |
| IO2 | 38 | I2C_SCL | 4.7 kΩ to +3V3 |
| IO4 | 4 | CELL_A0 | → U4 A |
| IO5 | 5 | CELL_A1 | → U4 B |
| IO6 | 6 | CELL_A2 | → U4 C |
| IO7 | 7 | CELL_A3 | → U4 D |
| IO8 | 12 | TAP_EN_n | **10 kΩ pull-up to +3V3** (taps off during reset) → U4 G1, U5 G1 |
| IO9 | 17 | ONEWIRE | 4.7 kΩ to +3V3, to CN2..CN5 pin 1 via 100 Ω |
| IO10 | 18 | ADC_CS | 10 kΩ pull-up to +3V3 → U6 CS |
| IO11 | 19 | ADC_DIN | → U6 DIN |
| IO12 | 20 | ADC_SCLK | → U6 SCLK |
| IO13 | 21 | ADC_DOUT | ← U6 DOUT/DRDY |
| IO14 | 22 | ADC_DRDY | ← U6 DRDY |
| IO15 | 8 | XFER_n | **10 kΩ pull-up to +3V3** → U5 G2A |
| IO16 | 9 | POL | → U5 A (10 kΩ pull-down) |
| IO17 | 10 | DISCH | → U5 B (10 kΩ pull-down) |
| IO18 | 11 | BAL_OE_n | **10 kΩ pull-up to +3V3** → U9 OE (balancing off during reset/crash) |
| IO21 | 23 | ACT_BAL_EN | 100 kΩ pull-down → J3.19 |
| IO38 | 31 | ACT_BAL_PWM | 100 kΩ pull-down → J3.20 |
| IO39 | 32 | LED_ERR | red LED + 820 Ω to +3V3 (active low) |
| IO40 | 33 | LED_USR | green LED + 390 Ω to +3V3 (active low) |
| IO41 | 34 | ADDR0 | DIP SW1.1 to +3V3, 100 kΩ pull-down |
| IO42 | 35 | ADDR1 | DIP SW1.2 to +3V3, 100 kΩ pull-down |
| IO47 | 24 | ADDR2 | DIP SW1.3 to +3V3, 100 kΩ pull-down |
| IO48 | 25 | ADDR3 | DIP SW1.4 to +3V3, 100 kΩ pull-down |
| IO19 | 13 | USB_D− | USB-C D− (A7/B7), ESD PRTR5V0U2X |
| IO20 | 14 | USB_D+ | USB-C D+ (A6/B6) |
| TXD0/RXD0 | 37/36 | UART0 | test pads only |
| 3V3 | 2 | +3V3 | 10 µF + 100 nF at the pin |
| GND | 1, 40, 41 | GND | |
| **Do not connect** | | | IO3, IO45, IO46 (strapping), IO35/36/37 (octal PSRAM) |

USB-C: CC1/CC2 5.1 kΩ to GND, VBUS → D3. Shield via 1 MΩ ∥ 4.7 nF to GND.
**USB GND = B−**: only connect a PC through a USB isolator once cells are connected.

1-Wire: CN2..CN5 3-pin (1 = ONEWIRE, 2 = +3V3, 3 = GND), as in 2.0.1.0.

J3 active balancer (20-pin, same pinout as 2.0.1.0 U18): 1 = T0_F, 2..17 = T1_F..T16_F,
18 = nc, 19 = ACT_BAL_EN, 20 = ACT_BAL_PWM. The tap fuses F0..F16 are sized for 1 A; increase them
if the active balancer moves more than ~0.8 A per cell.

---

## 3. Sheet CELL_INPUT

J1: 17-pin cell connector (+ spare pins, keep ≥ 1 mm spacing), pin n+1 = Tn.

Per tap j = 0..16:

| Part | From | To | Value |
|---|---|---|---|
| Fj | Tj (J1) | Tj_F | 1 A fast fuse 1206 (protects traces if a board part fails short) |
| RMj | Tj_F | Tj_M | 1 kΩ 1206, pulse-proof (anti-surge) |

`T0_F` is only a sense/balancing tap, **not** connected to GND (see net naming above).

String divider (plausibility check, AIN2):
`T16_F` – R10 510 kΩ – R11 510 kΩ – R12 510 kΩ – **VSTR_DIV** – R13 100 kΩ 0.1 % – GND, C10 100 nF on VSTR_DIV.
Ratio 16.3 → 58.4 V = 3.58 V (< 4.096 V). Three resistors in series because of the voltage rating of 0805.
Unused taps are bridged to the top tap, so `T16` always is the string top.

---

## 4. Sheet MEAS_MUX (core)

### 4.1 Tap switches (K1..K17, PhotoMOS ≥ 100 V)

Output side: pin 3/4 (bidirectional), LED side: pin 1 anode, pin 2 cathode.

| Tap | Switch | Output: from → to | LED anode | LED cathode |
|---|---|---|---|---|
| T0 | K1 | T0_M → BUS_A | R 560 Ω to +5V | U4 Y0 (direct) |
| T1 | K2 | T1_M → BUS_B | R 560 Ω to +5V | DT1 (BAT54A) → Y0, Y1 |
| T2 | K3 | T2_M → BUS_A | R 560 Ω to +5V | DT2 → Y1, Y2 |
| … | … | even taps → BUS_A, odd taps → BUS_B | | DTj → Y(j−1), Yj |
| T15 | K16 | T15_M → BUS_B | R 560 Ω to +5V | DT15 → Y14, Y15 |
| T16 | K17 | T16_M → BUS_A | R 560 Ω to +5V | U4 Y15 (direct) |

BAT54A = common anode: pin 3 (anode) ← LED cathode, pin 1 and pin 2 (cathodes) → the two decoder outputs.

**Cell k is selected by U4 output Y(k−1)**: that output turns on exactly taps k−1 and k
(one on BUS_A, one on BUS_B). Two non-adjacent taps can never be on together – no software bug
can put more than one cell across the capacitor.

U4 74HCT154 (supply +5V, 100 nF):

| Pin | Net |
|---|---|
| A, B, C, D | CELL_A0..CELL_A3 (3.3 V logic is fine for HCT inputs) |
| G1 | TAP_EN_n |
| G2 | GND |
| Y0..Y15 | per table above |

LED current: (5 V − 1.3 V LED − 0.35 V diode − ~0.4 V output) / 560 Ω ≈ 5 mA per switch, 10 mA per output.

### 4.2 Flying capacitor

C_FC: **1 µF, polypropylene film (MKP), ≥ 63 V**, between BUS_A and BUS_B.
No X7R/X5R (dielectric absorption). No other capacitors or resistors on BUS_A/BUS_B.

### 4.3 Transfer H-bridge (K18..K21, same PhotoMOS type as the tap switches)

| Switch | Output: from → to | LED cathode (anode via 560 Ω to +5V) | On in state |
|---|---|---|---|
| K18 (A_P) | BUS_A → FC_HI | U5 Y0 (direct) | even cell (BUS_A positive) |
| K19 (B_P) | BUS_B → FC_HI | U5 Y1 (direct) | odd cell (BUS_B positive) |
| K20 (A_G) | BUS_A → FC_GND | DX1 (BAT54A) → Y1, Y2 | odd cell, discharge |
| K21 (B_G) | BUS_B → FC_GND | DX2 (BAT54A) → Y0, Y2 | even cell, discharge |

U5 74HCT138 (supply +5V, 100 nF):

| Pin | Net |
|---|---|
| A | POL (1 = odd cell) |
| B | DISCH |
| C | GND |
| G1 (active high) | TAP_EN_n → transfer only possible while the tap decoder is disabled |
| G2A | XFER_n |
| G2B | GND |
| Y0 | even cell: A_P + B_G |
| Y1 | odd cell: B_P + A_G |
| Y2 | discharge: A_G + B_G |
| Y3..Y7 | nc |

`FC_GND` is a separate trace to the star point (GND sense for ADC AIN1), joined to GND by a net tie
next to the ADC.

Overlap safety (firmware waits ≥ 1 ms between switching off and on): if tap and transfer switches
overlapped anyway, the current is limited by the 1 kΩ tap resistors (≤ 60 mA for < 1 ms) and the
10 kΩ buffer input resistor (≤ 6 mA into the OPA333 input clamp).

---

## 5. Sheet ADC

| Part | Pin | Net |
|---|---|---|
| R20 10 kΩ | | FC_HI → BUF_IN |
| U8 OPA333AIDBV (supply +5VA, 100 nF) | +IN | BUF_IN |
| | −IN, OUT | BUF_OUT (unity-gain follower) |
| | V− | GND |
| R21 100 Ω, C21 10 nF C0G | | BUF_OUT → AIN0_F, 10 nF to GND |
| R22 100 Ω, C22 10 nF C0G | | FC_GND → AIN1_F, 10 nF to GND |
| U6 ADS1220IPW (TSSOP-16) | AIN0/REFP1 | AIN0_F |
| | AIN1 | AIN1_F |
| | AIN2 | VSTR_DIV |
| | AIN3/REFN1 | NTC_DIV |
| | REFP0 | VREF (4.096 V) |
| | REFN0 | GND |
| | AVDD | +5VA (100 nF + 1 µF) |
| | AVSS | GND |
| | DVDD | +3V3 (100 nF) → logic levels 3.3 V |
| | DGND | GND |
| | CLK | GND (internal oscillator) |
| | SCLK, CS, DIN | ADC_SCLK, ADC_CS, ADC_DIN |
| | DOUT/DRDY | ADC_DOUT |
| | DRDY | ADC_DRDY |
| U7 REF5040 (SOIC-8/MSOP-8) | VIN | +5VA (1 µF) |
| | VOUT | VREF, 10 µF X7R + 100 nF |
| | TRIM/NR | 1 µF to GND (noise reduction) |
| | GND | GND |
| | TEMP, DNC | nc |
| R23 10 kΩ 0.1 % | | VREF → NTC_DIV |
| RT1 NTC 10 kΩ B3950 | | NTC_DIV → GND, **placed between the bleed resistors** |
| C23 100 nF | | NTC_DIV → GND |

ADS1220 configuration: PGA bypassed, gain 1, reference REFP0/REFN0 (4.096 V), single-shot, 330 SPS.
AIN0−AIN1 = cell voltage (0 … 4.096 V). Die temperature from the internal sensor.

---

## 6. Sheet BALANCING

U9 PCA9685PW (supply **+3V3**, so I2C and output levels are 3.3 V):

| Pin | Net |
|---|---|
| A0..A5 | GND → address 0x40 |
| SDA, SCL | I2C_SDA, I2C_SCL |
| OE | BAL_OE_n (10 kΩ pull-up → all outputs low when ESP32 is in reset or not driving) |
| EXTCLK | GND |
| VDD | +3V3 (100 nF + 10 µF) |
| VSS | GND |
| LED0..LED15 | channel 1..16 |

Per channel n = 1..16 (cell n between `T(n−1)_F` and `Tn_F`):

| Part | Connection |
|---|---|
| RBn 390 Ω | LED(n−1) → KBn LED anode, KBn LED cathode → GND (≈ 5 mA, totem-pole output) |
| LEDn + 1 kΩ (optional) | LED(n−1) → indicator LED → GND |
| KBn PhotoMOS (e.g. GAQY211G2EH as in 2.0.1.0) | output: T(n−1)_F → BLn |
| RBLn_a, RBLn_b 33 Ω 2512 1 W | BLn → Tn_F (in parallel = 16.5 Ω) |

Bleed current 3.3 V / 16.5 Ω ≈ 200 mA (0.22 A at 3.65 V), 0.4 W per resistor = 40 % of rating.
All 16 on: ~13 W → spread the resistors over the board and keep the NTC in the middle.

---

## 7. Bill of materials (main parts)

| Ref | Qty | Part | Notes |
|---|---|---|---|
| U1 | 1 | ESP32-S3-WROOM-1-N8R8 | |
| U2 | 1 | LM5164DDA | 100 V buck |
| U3 | 1 | TLV75733PDBV | 3.3 V 1 A LDO |
| U4 | 1 | 74HCT154 (SOIC-24/TSSOP-24) | cell select |
| U5 | 1 | 74HCT138 | transfer select |
| U6 | 1 | ADS1220IPW | |
| U7 | 1 | REF5040 (A or I grade) | |
| U8 | 1 | OPA333AIDBV | zero-drift buffer |
| U9 | 1 | PCA9685PW | |
| K1..K21 | 21 | AQY280S (350 V, 25 Ω, SO-4) | measurement matrix |
| KB1..KB16 | 16 | AQY282GS (60 V, 0.8 A, 0.8 Ω, SO-4) | balancing |
| DT1..DT15, DX1, DX2 | 17 | BAT54A (SOT-23, common anode) | diode-OR |
| C_FC | 1 | 1 µF MKP polypropylene ≥ 63 V | flying capacitor |
| RM0..RM16 | 17 | 1 kΩ 1206 pulse-proof | tap series |
| F0..F16 | 17 | 1 A fast fuse 1206 | tap fuses |
| RBL | 32 | 33 Ω 2512 1 W | bleed |
| RT1 | 1 | NTC 10 kΩ B3950 0603 | bleed temperature |
| D1 | 1 | Schottky 100 V 1 A (SMA) | reverse polarity |
| D2 | 1 | SMBJ60A | TVS |
| SW1 | 1 | 4-pos DIP | string address |

---

## 8. Layout rules

1. Net classes `HV` / `BAL` (all tap, bus, string and bleed nets): DRC clearance 0.6 mm (IPC-2221 B2,
   ≤ 150 V, uncoated). Keep ≥ 1 mm between tap traces wherever the layout allows.
2. Keep the measurement matrix, C_FC, buffer and ADC in one compact area. Guard ring (GND) around
   BUS_A/BUS_B/C_FC/BUF_IN to keep leakage currents away.
3. Star ground: FC_GND (net tie), ADC AVSS/REFN0, REF5040 GND meet at one point. Power return (J2.2)
   and the buck current loop must not flow through it.
4. Balancing current (0.2 A per cell) only on the T_F → KB → RBL path, never through the 1 kΩ / matrix path.
5. Bleed resistors on the board edge with copper pours for heat spreading, NTC in between.
6. Buck converter away from the ADC, keep its switching loop small.
7. Antenna keep-out of the ESP32-S3-WROOM-1 at the board edge.

---

## 9. Measurement sequence (firmware) and expected accuracy

Per scan (balancing paused with BAL_OE_n = 1, wait 5 ms for the tap wires to settle):

Order: **odd cells first, then even cells** – the capacitor keeps the same polarity, so dielectric
absorption has no effect.

For each cell k:

1. XFER_n = 1, POL = 0, DISCH = 1, XFER_n = 0 → capacitor discharged (≥ 1 ms), XFER_n = 1, wait 1 ms.
2. CELL_A = k − 1, TAP_EN_n = 0 → capacitor charges to cell k (25 ms ≈ 12 τ, τ ≈ 2 kΩ × 1 µF).
3. TAP_EN_n = 1, wait 1 ms (switch turn-off).
4. POL = k & 1, DISCH = 0, XFER_n = 0, wait 2 ms (switch turn-on, buffer settling).
5. ADS1220 single-shot AIN0−AIN1 (~3.5 ms) → V_cell.
6. XFER_n = 1.

≈ 35 ms per cell, ≈ 0.6 s per 16-cell scan (+ AIN2 string voltage, AIN3 NTC, die temperature).

Diagnostics:
- **Open tap wire**: capacitor stays at ~0 V after step 2 → reading ≈ 0 V.
- **Stuck tap switch**: discharge, keep TAP_EN_n = 1 for 50 ms, transfer → must still read ≈ 0 V.
- **Plausibility**: sum of all cells vs. AIN2 string voltage (±1 %).
- **Offset**: discharge state (Y2) read through the buffer = system offset.

Error estimate (one-point gain calibration per board, ±20 K):

| Source | Error |
|---|---|
| REF5040 drift (3–8 ppm/K) | 0.2–0.5 mV |
| ADS1220 noise at 330 SPS, INL | < 0.1 mV |
| OPA333 offset (10 µV, zero drift) | < 0.01 mV |
| Charging settling (12 τ) | < 0.1 mV |
| PhotoMOS leakage (typ. nA) during transfer | ~0.1 mV |
| **Total** | **< 1 mV typ., same for every cell** |

Compared to 2.0.1.0: no divider drift (10–40 mV on the top cells), no quiescent cell load,
1 ADC instead of 12, and the balancing outputs are off in hardware during reset.

---

## 10. Check before ordering

- [x] PhotoMOS for K1..K21: AQY280S (350 V). Still check off-state leakage and LED trigger current (≤ 3 mA).
- [ ] LM5164 values (R1–R3, L1) with WEBENCH for 10–60 V in, 5 V / 0.6 A out.
- [x] Symbols and pins: verified automatically (KiCad ERC clean, schematic netlist == SKiDL netlist).
- [ ] Cell connector J1 / balancer header J3: placeholder Degson screw-terminal footprints, replace with the
      pluggable 3.5 mm header (15EDGRC-3.5) via easyeda2kicad.
- [ ] Footprints: C_FC (film capacitor size), 2512 bleed resistors, SOP-4 PhotoMOS.
- [x] DRC net classes HV/BAL (0.6 mm) and 0.2 mm minimum hole are set in the KiCad project.
- [ ] Prototype first with 4 cells and a bench supply.
