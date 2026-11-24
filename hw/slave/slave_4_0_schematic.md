# CALU BMS Slave 4.0 – Schematic specification for EasyEDA

| | |
|---|---|
| Status | 0.2 – updated with the decisions of review 1 (work item W-07, issue #8) |
| Requirements | [slave requirements](../../docs/slave_requirements.md) 0.6, [slave architecture](../../docs/slave_architecture.md) |
| Basis | slave 3.0.0.0 (branch `slave-hw-3.0.0.0`, KiCad/SKiDL, ERC clean), updated per section 2 |
| Reference netlist | [slave_4_0_netlist.csv](slave_4_0_netlist.csv) – every pin of every part (sheet, ref, pin, pin name, net) |

Once the schematic is drawn, the EasyEDA project becomes the source of truth. The reference netlist is used
to check the drawing automatically (section 15).

---

## 1. How to draw this in EasyEDA

1. **One schematic page per sheet** of this document: POWER, MCU, CELLS, MEAS_MUX, ADC, BALANCING.
2. **Use the designators of this document** (R101, K401, …: hundred block per sheet). The automatic check
   (section 15) compares by designator.
3. **Use net labels with exactly the net names of the tables.** Nets that connect more than one page are
   listed in section 4; they need the same net label on every page (EasyEDA connects equal net labels across
   pages). Local nets (e.g. `K401_LED`) can be drawn as wires; their names are only for reading the tables.
4. **Pins:** ICs and connectors are listed pin by pin (datasheet pin numbers). For diodes and LEDs the
   tables give **A/K** (anode/cathode), for polarised capacitors **+/−** – EasyEDA library symbols do not
   always number these pins the same way. Unused pins are listed as `nc` → place a no-connect flag.
5. **Parts:** place parts from the LCSC library with the LCSC number given; generic resistors/capacitors by
   value, package, tolerance and voltage from the tables (JLCPCB basic parts where possible).
6. **Repeated channels** (17 taps, 16 balancing channels): draw one channel, check it against the table,
   then copy it and change designators and net labels.

---

## 2. Changes from slave 3.0.0.0

| # | Change | Reason |
|---|---|---|
| 1 | Buck regulator **LM5164-Q1** (LM5164QDDARQ1, same die and pinout) | LM5164DDA has no stock at JLCPCB |
| 2 | **Type-3 ripple injection** added to the buck (R106, C113, C114) | the COT control needs ≥ 20 mV ripple at FB (datasheet); 3.0 had none → unstable with ceramic output capacitors |
| 3 | Buck values calculated: R101/R102 (UVLO 9.0 V on / 8.4 V off), R103 41.2 kΩ (303 kHz), L101 68 µH | 3.0 values were placeholders |
| 4 | Reference **REF5045** (4.5 V) instead of REF5040 | SHW-003: cell range ≥ 4.5 V (4.096 V clipped) |
| 5 | Flying capacitor **470 nF** polypropylene (THT, Panasonic ECWFD2W474Q1) instead of 1 µF | SHW-005: scan ≤ 0.5 s (3.0: ≈ 0.6 s); no SMD PP part in stock |
| 6 | NTC NCP18XH103F03RB (B = 3434 K) instead of a B3950 type | stock; firmware uses the B value of this part |
| 7 | Cell connector 18-pin 3.5 mm pluggable (DB2ERC-3.5-18P), power connector 2-pin same series | 3.0 placeholder footprints |
| 8 | Mounting holes M4 plated, nylon screws/spacers, insulating enclosure (review 1) | SHW-060/061: reinforced insulation (600 V) to the enclosure |
| 9 | Test point TP301 at VSTR_DIV | SHW-064 |
| 10 | No analog load switch (planned in the architecture) | not needed: low-power budget is met without it (section 9.1) |
| 11 | Readable names for all local nets | drawing aid |
| 12 | Connectors MX15EDGRM-3.5 pluggable series (J101, J301…J306), USB-C TYPE-C 16PIN 2MD(073), 6 × 6 mm push buttons, 2.54 mm DIP switch, PRTR5V0U2X C21713980, 22 µF 25 V output capacitors (review 1) | chosen while drawing; all in stock |
| 13 | Address LEDs D230…D233 with 4.7 kΩ (R226…R232), pull-downs renamed R225…R231; LED resistors R213/R214 1 kΩ (review 1) | address visible on the board; 4.7 kΩ keeps the low-power budget (section 12.1) |
| 14 | Star point `FC_GND` – `GND` through R504 0 Ω instead of the net tie NT501 (review 1) | EasyEDA; keeps the star point visible for the layout |

Everything else (measurement matrix, decoders, ADC, balancing, MCU pinout) is unchanged from 3.0.

---

## 3. Block diagram

```
         J301 (cell taps T0..T16)                    J101 (power B+ / B−)
                 │                                          │
        ┌────────┴─────────┐                         F101, D101, D102 (TVS)
        │ per tap: fuse    │                                │
        └──┬───────────┬───┘                LM5164-Q1 100 V buck → +5V ──► TLV75733 → +3V3
           │           │                                   │            └► FB101 → +5VA (analog)
   BALANCING (600)     │ MEAS_MUX (400)
   16 × AQY282 +       │   1 kΩ per tap ─► 17 × AQY280 ─► BUS_A (even taps) / BUS_B (odd taps)
   2 × 33 Ω per cell   │                   driven by 74HCT154 + BAT54A diode-OR (hardware: only
   driven by PCA9685   │                   the 2 taps of ONE cell can be on)
   OE pulled high      │                           │
   = off at reset      │                   C402 470 nF PP film between BUS_A and BUS_B
                       │                           │
                       │                   4 × AQY280 transfer H-bridge (74HCT138, only when
                       │                   all tap switches are off) ─► FC_HI / FC_GND
                       │                           │
                       │                   ADC (500): 10 kΩ ─► OPA333 buffer ─► ADS1220 AIN0
                       │                   AIN2 = module voltage divider, AIN3 = NTC at bleed resistors
                       │                           │ SPI
                       └──────────────────► ESP32-S3 (200) ◄── I²C ── PCA9685
```

Net naming: `T0…T16` = cell taps at the connector (`T0` = module negative, `Tn` = + of cell n), `Tn_F` = after
the tap fuse, `Tn_M` = after the 1 kΩ measurement resistor. `GND` = board ground = module negative, connected
**only** through the power connector J101 pin 2; `T0` is **not** connected to GND on the board (the flying
capacitor measures every cell floating, and the supply current must not flow through the T0 sense wire).

---

## 4. Nets between pages (net labels)

| Net | Pages | Net | Pages |
|---|---|---|---|
| `+3V3` | POWER, MCU, CELLS, ADC, BALANCING | `CELL_A3` | MCU, MEAS_MUX |
| `+5V` | POWER, MEAS_MUX | `DISCH` | MCU, MEAS_MUX |
| `+5VA` | POWER, ADC | `FC_GND` | MEAS_MUX, ADC |
| `GND` | POWER, MCU, CELLS, MEAS_MUX, ADC, BALANCING | `FC_HI` | MEAS_MUX, ADC |
| `VBUS` | POWER, MCU | `I2C_SCL` | MCU, BALANCING |
| `ACT_BAL_EN` | MCU, CELLS | `I2C_SDA` | MCU, BALANCING |
| `ACT_BAL_PWM` | MCU, CELLS | `NTC_DIV` | ADC, BALANCING |
| `ADC_CS` | MCU, ADC | `ONEWIRE` | MCU, CELLS |
| `ADC_DIN` | MCU, ADC | `POL` | MCU, MEAS_MUX |
| `ADC_DOUT` | MCU, ADC | `TAP_EN_n` | MCU, MEAS_MUX |
| `ADC_DRDY` | MCU, ADC | `VREF` | ADC, BALANCING |
| `ADC_SCLK` | MCU, ADC | `VSTR_DIV` | CELLS, ADC |
| `BAL_OE_n` | MCU, BALANCING | `XFER_n` | MCU, MEAS_MUX |
| `CELL_A0` | MCU, MEAS_MUX | `T0_F` … `T16_F` (17 nets) | CELLS, BALANCING |
| `CELL_A1` | MCU, MEAS_MUX | `T0_M` … `T16_M` (17 nets) | CELLS, MEAS_MUX |
| `CELL_A2` | MCU, MEAS_MUX |  |  |

---

## 5. Sheet POWER (100)

```
J101.1 (B+) ─ F101 0.5 A ─ D101 (SS110, reverse polarity) ─┬─ VIN_HV ── U101 LM5164-Q1 ── L101 ─┬─ +5V ─ U102 TLV75733 ─ +3V3
J101.2 (B−) ─ GND                         D102 SMAJ60A (TVS)┤                 ripple: R106/C113/C114 ├─ FB101 ─ +5VA
                                          C101 22 µF + C102/C103 2.2 µF + C104                  VBUS ─ D103 ─┘ (USB only)
```

Buck design (datasheet SNVSAU4D equations, V<sub>IN</sub> 10…60 V, V<sub>OUT</sub> 5 V, ≤ 0.5 A):

| Item | Value | Calculation |
|---|---|---|
| Output voltage | 4.99 V (+≈ 0.04 V from the ripple network) | 1.2 V × (1 + R104/R105) = 1.2 × (1 + 316k/100k) |
| Switching frequency | 303 kHz | R103 = 5 V × 2500 / f[kHz] → 41.2 kΩ; t<sub>ON</sub> at 60 V = 275 ns > 50 ns minimum |
| Inductor | 68 µH, I<sub>sat</sub> ≥ 1.8 A (current limit 1.75 A max) | ΔI<sub>L</sub> = 0.22 A at 48 V |
| Output capacitors | 2 × 22 µF 10 V X7R | ≥ ΔI<sub>L</sub> / (8 f ΔV) = 3.6 µF for 25 mV |
| Ripple network (Type 3) | R106 200 kΩ (0805), C113 3.3 nF, C114 100 pF C0G | C113 ≥ 10 / (f × R104‖R105) = 0.43 nF; FB ripple 12.5 mV at 10 V, 22 mV at 48 V, 23 mV at 60 V |
| UVLO | on 8.96 V, off 8.37 V | R101 2 MΩ / R102 402 kΩ, EN thresholds 1.5 V / 1.4 V; divider current 24 µA |
| Input protection | F101 0.5 A 63 V, D101 SS110 (100 V), D102 SMAJ60A (standoff 60 V, clamp < 100 V) | max. module voltage 16 × 3.65 V = 58.4 V |

**J101** B+ / B− · 3.5 mm pluggable 2P · MX15EDGRM-3.5-02P-GN01-Cu-A · C5188341 – 1 = B+ (module top, own wire), 2 = B− (module negative, own wire)

| Pin | Name | Net |
|---|---|---|
| 1 | B+ | `B_PLUS` |
| 2 | B− | `GND` |

**U101** LM5164-Q1 · SO-8 PowerPAD · LM5164QDDARQ1 · C2072225

| Pin | Name | Net |
|---|---|---|
| 1 | GND | `GND` |
| 2 | VIN | `VIN_HV` |
| 3 | EN/UVLO | `BUCK_EN` |
| 4 | RON | `BUCK_RON` |
| 5 | FB | `BUCK_FB` |
| 6 | PGOOD | `BUCK_PGOOD` |
| 7 | BST | `BUCK_BST` |
| 8 | SW | `BUCK_SW` |
| 9 | EP (thermal pad) | `GND` |

**U102** TLV75733PDBV · SOT-23-5 · TLV75733PDBVR · C485517

| Pin | Name | Net |
|---|---|---|
| 1 | IN | `+5V` |
| 2 | GND | `GND` |
| 3 | EN | `+5V` |
| 4 | NC | nc |
| 5 | OUT | `+3V3` |

**Two-terminal parts and test points**

| Ref | Value | Package | Part · LCSC | Connection | Note |
|---|---|---|---|---|---|
| C101 | 22uF 100V | SMD D6.3 mm | RVT100V22M6X8 · C47023097 | +: `VIN_HV` · −: `GND` |  |
| C102 | 2.2uF 100V | 1210 | TCC1210X7R225K101MT · C5449052 | `VIN_HV` – `GND` |  |
| C103 | 2.2uF 100V | 1210 | TCC1210X7R225K101MT · C5449052 | `VIN_HV` – `GND` |  |
| C104 | 100nF 100V | 0603 | 0603B104K101NT · C88219 | `VIN_HV` – `GND` |  |
| C105 | 2.2nF | 0603 | CC0603KRX7R9BB222 · C107082 | `BUCK_BST` – `BUCK_SW` |  |
| C106 | 22uF 25V | 1206 | CL31A226KAHNNNE · C12891 | `+5V` – `GND` |  |
| C107 | 22uF 25V | 1206 | CL31A226KAHNNNE · C12891 | `+5V` – `GND` |  |
| C108 | 10uF | 0603 |  | `+5VA` – `GND` | X7R/X5R ≥ 10 V |
| C109 | 100nF | 0603 |  | `+5VA` – `GND` | X7R/X5R ≥ 10 V |
| C110 | 1uF | 0603 |  | `+5V` – `GND` | X7R/X5R ≥ 10 V |
| C111 | 10uF | 0603 |  | `+3V3` – `GND` | X7R ≥ 10 V |
| C112 | 100nF | 0603 |  | `+3V3` – `GND` | X7R ≥ 10 V |
| C113 | 3.3nF | 0603 | CC0603KRX7R9BB332 · C107088 | `BUCK_RIP` – `+5V` | ripple injection C_A, X7R ≥ 16 V |
| C114 | 100pF | 0603 |  | `BUCK_RIP` – `BUCK_FB` | X7R ≥ 10 V, ripple injection C_B, C0G |
| D101 | SS110 | SMA | SS110 · C2482 | K: `VIN_HV` · A: `B_PLUS_F` |  |
| D102 | SMAJ60A | SMA | SMAJ60A-13-F · C135002 | K: `VIN_HV` · A: `GND` |  |
| D103 | PMEG6020 | SOD-123F | PMEG6020ER · C2687553 | K: `+5V` · A: `VBUS` |  |
| F101 | 0.5A fast | 1206 | 0466.500NRHF · C151133 | `B_PLUS` – `B_PLUS_F` |  |
| FB101 | 600R@100MHz | 0603 |  | `+5V` – `+5VA` |  |
| L101 | 68uH | 10 × 10 mm | YNR1050-680M · C5174473 | `BUCK_SW` – `+5V` | I_sat ≥ 1.8 A |
| R101 | 2M | 0805 | 0805W8F2004T5E · C26112 | `VIN_HV` – `BUCK_EN` | UVLO: on 8.96 V, off 8.37 V |
| R102 | 402k | 0603 | 0603WAF4023T5E · C23048 | `BUCK_EN` – `GND` | 1 %, UVLO |
| R103 | 41.2k | 0603 | 0603WAF4122T5E · C23166 | `BUCK_RON` – `GND` | 1 %, f_SW = 303 kHz |
| R104 | 316k | 0603 | 0603WAF3163T5E · C25814 | `+5V` – `BUCK_FB` | 1 %, feedback |
| R105 | 100k | 0603 |  | `BUCK_FB` – `GND` | 1 %, feedback |
| R106 | 200k | 0805 | 0805W8F2003T5E · C17539 | `BUCK_SW` – `BUCK_RIP` | ripple injection R_A, 1 % |
| TP101 | PGOOD | – |  | `BUCK_PGOOD` |  |
| TP102 | +5V | – |  | `+5V` |  |
| TP103 | +5VA | – |  | `+5VA` |  |
| TP104 | +3V3 | – |  | `+3V3` |  |
| TP105 | GND | – |  | `GND` |  |
| TP106 | VIN_HV | – |  | `VIN_HV` |  |

---

## 6. Sheet MCU (200)

ESP32-S3-WROOM-1-N8R8. Module pins with their GPIO:

| GPIO | Module pin | Net | Notes |
|---|---|---|---|
| EN | 3 | EN | 10 kΩ to +3V3, 1 µF to GND, reset button |
| IO0 | 27 | BOOT | 10 kΩ to +3V3, boot button |
| IO1 / IO2 | 39 / 38 | I2C_SDA / I2C_SCL | 4.7 kΩ to +3V3 |
| IO4…IO7 | 4…7 | CELL_A0…CELL_A3 | cell select |
| IO8 | 12 | TAP_EN_n | **10 kΩ pull-up**: taps off in reset and deep sleep |
| IO9 | 17 | ONEWIRE | 4.7 kΩ to +3V3 |
| IO10…IO14 | 18…22 | ADC_CS (10 kΩ pull-up), ADC_DIN, ADC_SCLK, ADC_DOUT, ADC_DRDY | SPI to ADS1220 |
| IO15 | 8 | XFER_n | **10 kΩ pull-up**: transfer off in reset |
| IO16 / IO17 | 9 / 10 | POL / DISCH | 10 kΩ pull-down |
| IO18 | 11 | BAL_OE_n | **10 kΩ pull-up**: balancing off in reset/crash/sleep |
| IO21 / IO38 | 23 / 31 | ACT_BAL_EN / ACT_BAL_PWM | 100 kΩ pull-down |
| IO39 / IO40 | 32 / 33 | LED_ERR / LED_USR | LEDs to +3V3, active low |
| IO41, IO42, IO47, IO48 | 34, 35, 24, 25 | ADDR0…ADDR3 | DIP to +3V3, 100 kΩ pull-down, address LED (4.7 kΩ + LED to GND) |
| IO19 / IO20 | 13 / 14 | USB_D− / USB_D+ | native USB |
| TXD0 / RXD0 | 37 / 36 | TXD0 / RXD0 | test points |
| **nc** | 15, 16, 26, 28, 29, 30 | – | IO3, IO46, IO45 (strapping), IO35…IO37 (octal PSRAM) |

USB GND = module negative: with cells connected, connect a PC **only through a USB isolator ≥ 1 kV** (SAF-013).

**D203** PRTR5V0U2X · SOT-143 · PRTR5V0U2X · C21713980

| Pin | Name | Net |
|---|---|---|
| 1 | GND | `GND` |
| 2 | I/O1 | `USB_D+` |
| 3 | I/O2 | `USB_D-` |
| 4 | VCC | `VBUS` |

**J201** USB-C · USB-C 16P SMD · TYPE-C 16PIN 2MD(073) · C2765186

| Pin | Name | Net |
|---|---|---|
| SH | shield | `USB_SHIELD` |
| A1 | GND | `GND` |
| B1 | GND | `GND` |
| A4 | VBUS | `VBUS` |
| B4 | VBUS | `VBUS` |
| A5 | CC1 | `USB_CC1` |
| B5 | CC2 | `USB_CC2` |
| A6 | D+ | `USB_D+` |
| B6 | D+ | `USB_D+` |
| A7 | D− | `USB_D-` |
| B7 | D− | `USB_D-` |
| A8 | SBU1 | nc |
| B8 | SBU2 | nc |
| A9 | VBUS | `VBUS` |
| B9 | VBUS | `VBUS` |
| A12 | GND | `GND` |
| B12 | GND | `GND` |

**SW203** ADDR · DIP-4 SMD 2.54 mm · 2.54-4P TPGT · C6331176

| Pin | Name | Net |
|---|---|---|
| 1 | SW1 a | `+3V3` |
| 2 | SW2 a | `+3V3` |
| 3 | SW3 a | `+3V3` |
| 4 | SW4 a | `+3V3` |
| 5 | SW4 b | `ADDR3` |
| 6 | SW3 b | `ADDR2` |
| 7 | SW2 b | `ADDR1` |
| 8 | SW1 b | `ADDR0` |

**U201** ESP32-S3-WROOM-1-N8R8 · module · ESP32-S3-WROOM-1-N8R8 · C2913201

| Pin | Name | Net |
|---|---|---|
| 1 | GND | `GND` |
| 2 | 3V3 | `+3V3` |
| 3 | EN | `EN` |
| 4 | IO4 | `CELL_A0` |
| 5 | IO5 | `CELL_A1` |
| 6 | IO6 | `CELL_A2` |
| 7 | IO7 | `CELL_A3` |
| 8 | IO15 | `XFER_n` |
| 9 | IO16 | `POL` |
| 10 | IO17 | `DISCH` |
| 11 | IO18 | `BAL_OE_n` |
| 12 | IO8 | `TAP_EN_n` |
| 13 | IO19 | `USB_D-` |
| 14 | IO20 | `USB_D+` |
| 15 | IO3 | nc |
| 16 | IO46 | nc |
| 17 | IO9 | `ONEWIRE` |
| 18 | IO10 | `ADC_CS` |
| 19 | IO11 | `ADC_DIN` |
| 20 | IO12 | `ADC_SCLK` |
| 21 | IO13 | `ADC_DOUT` |
| 22 | IO14 | `ADC_DRDY` |
| 23 | IO21 | `ACT_BAL_EN` |
| 24 | IO47 | `ADDR2` |
| 25 | IO48 | `ADDR3` |
| 26 | IO45 | nc |
| 27 | IO0 | `BOOT` |
| 28 | IO35 | nc |
| 29 | IO36 | nc |
| 30 | IO37 | nc |
| 31 | IO38 | `ACT_BAL_PWM` |
| 32 | IO39 | `LED_ERR` |
| 33 | IO40 | `LED_USR` |
| 34 | IO41 | `ADDR0` |
| 35 | IO42 | `ADDR1` |
| 36 | RXD0 | `RXD0` |
| 37 | TXD0 | `TXD0` |
| 38 | IO2 | `I2C_SCL` |
| 39 | IO1 | `I2C_SDA` |
| 40 | GND | `GND` |
| 41 | EPAD (GND) | `GND` |

**Two-terminal parts and test points**

| Ref | Value | Package | Part · LCSC | Connection | Note |
|---|---|---|---|---|---|
| C201 | 10uF | 0603 |  | `+3V3` – `GND` | X7R ≥ 10 V |
| C202 | 100nF | 0603 |  | `+3V3` – `GND` | X7R ≥ 10 V |
| C203 | 100nF | 0603 |  | `+3V3` – `GND` | X7R ≥ 10 V |
| C204 | 1uF | 0603 |  | `EN` – `GND` | X7R ≥ 10 V |
| C205 | 4.7nF | 0603 |  | `USB_SHIELD` – `GND` | X7R ≥ 10 V |
| D201 | red | 0603 | KT-0603R · C2286 | K: `LED_ERR` · A: `LED_RED_A` |  |
| D202 | green | 0603 |  | K: `LED_USR` · A: `LED_GREEN_A` |  |
| D230 | red/green | LED_0603 |  | K: `GND` · A: `D230_A` | address bit indicator |
| D231 | red/green | LED_0603 |  | K: `GND` · A: `D231_A` | address bit indicator |
| D232 | red/green | LED_0603 |  | K: `GND` · A: `D232_A` | address bit indicator |
| D233 | red/green | LED_0603 |  | K: `GND` · A: `D233_A` | address bit indicator |
| R201 | 10k | 0603 |  | `+3V3` – `EN` |  |
| R202 | 10k | 0603 |  | `+3V3` – `BOOT` |  |
| R203 | 10k | 0603 |  | `+3V3` – `TAP_EN_n` |  |
| R204 | 10k | 0603 |  | `+3V3` – `XFER_n` |  |
| R205 | 10k | 0603 |  | `+3V3` – `BAL_OE_n` |  |
| R206 | 10k | 0603 |  | `+3V3` – `ADC_CS` |  |
| R207 | 10k | 0603 |  | `POL` – `GND` |  |
| R208 | 10k | 0603 |  | `DISCH` – `GND` |  |
| R209 | 100k | 0603 |  | `ACT_BAL_EN` – `GND` |  |
| R210 | 100k | 0603 |  | `ACT_BAL_PWM` – `GND` |  |
| R211 | 4.7k | 0603 |  | `+3V3` – `I2C_SDA` |  |
| R212 | 4.7k | 0603 |  | `+3V3` – `I2C_SCL` |  |
| R213 | 1k | 0603 |  | `+3V3` – `LED_RED_A` |  |
| R214 | 1k | 0603 |  | `+3V3` – `LED_GREEN_A` |  |
| R219 | 4.7k | 0603 |  | `+3V3` – `ONEWIRE` |  |
| R220 | 5.1k | 0603 |  | `USB_CC1` – `GND` |  |
| R221 | 5.1k | 0603 |  | `USB_CC2` – `GND` |  |
| R222 | 1M | 0603 |  | `USB_SHIELD` – `GND` |  |
| R225 | 100k | 0603 |  | `ADDR0` – `GND` |  |
| R226 | 4.7k | 0603 |  | `D230_A` – `ADDR0` | address LED, ≈ 0.28 mA |
| R227 | 100k | 0603 |  | `ADDR1` – `GND` |  |
| R228 | 4.7k | 0603 |  | `D231_A` – `ADDR1` | address LED, ≈ 0.28 mA |
| R229 | 100k | 0603 |  | `ADDR2` – `GND` |  |
| R230 | 4.7k | 0603 |  | `D232_A` – `ADDR2` | address LED, ≈ 0.28 mA |
| R231 | 100k | 0603 |  | `ADDR3` – `GND` |  |
| R232 | 4.7k | 0603 |  | `D233_A` – `ADDR3` | address LED, ≈ 0.28 mA |
| SW201 | RESET | 6 × 6 mm SMD, 4 pads | 1TS005F-2500-5001 · C255812 | `EN` – `GND` |  |
| SW202 | BOOT | 6 × 6 mm SMD, 4 pads | 1TS005F-2500-5001 · C255812 | `BOOT` – `GND` |  |
| TP201 | TXD0 | – |  | `TXD0` |  |
| TP202 | RXD0 | – |  | `RXD0` |  |

---

## 7. Sheet CELLS (300)

- Per tap j = 0…16: fuse F30(j+1) 1 A 63 V (`Tj` → `Tj_F`), then R30(j+1) 1 kΩ 1206 (`Tj_F` → `Tj_M`).
  The balancing current only flows through the fuse (`Tj_F`), never through the 1 kΩ measurement path.
- Module voltage divider for the plausibility check: `T16_F` – 3 × 510 kΩ (0805, voltage rating) – `VSTR_DIV`
  – 100 kΩ 0.1 % – GND. Ratio 16.3: 58.4 V → 3.58 V, 72 V (16 × 4.5 V) → 4.42 V < 4.5 V reference.
  Unused taps are bridged to the top tap in the harness, so `T16` always is the module top.
- The board fuses protect the board traces (interrupting rating 50 A). The harness itself should have a fuse
  at the cell end of every sense wire (recommended for the cell harness, not part of this board).
- Connectors: J301 cell taps (pin 18 spare), J302 active balancer control, J303…J306 DS18B20 (1 = data,
  2 = +3V3, 3 = GND).

**J301** CELL TAPS · 3.5 mm pluggable 18P · MX15EDGRM-3.5-18P-GN01-Cu-A · C5188355 – pin n+1 = Tn, pin 18 spare

| Pin | Name | Net |
|---|---|---|
| 1 | T0 | `T0` |
| 2 | T1 | `T1` |
| 3 | T2 | `T2` |
| 4 | T3 | `T3` |
| 5 | T4 | `T4` |
| 6 | T5 | `T5` |
| 7 | T6 | `T6` |
| 8 | T7 | `T7` |
| 9 | T8 | `T8` |
| 10 | T9 | `T9` |
| 11 | T10 | `T10` |
| 12 | T11 | `T11` |
| 13 | T12 | `T12` |
| 14 | T13 | `T13` |
| 15 | T14 | `T14` |
| 16 | T15 | `T15` |
| 17 | T16 | `T16` |
| 18 | spare | nc |

**J302** ACT BAL CTRL · 3.5 mm pluggable 4P · MX15EDGRM-3.5-04P-GN01-Cu-A · C5188343

| Pin | Name | Net |
|---|---|---|
| 1 | GND | `GND` |
| 2 | +3V3 | `+3V3` |
| 3 | EN | `ACT_BAL_EN_OUT` |
| 4 | PWM | `ACT_BAL_PWM_OUT` |

**J303** DS18B20 · 3.5 mm pluggable 3P · MX15EDGRM-3.5-03P-GN01-Cu-A · C5188342

| Pin | Name | Net |
|---|---|---|
| 1 | DQ | `ONEWIRE_BUS` |
| 2 | VDD | `+3V3` |
| 3 | GND | `GND` |

**J304** DS18B20 · 3.5 mm pluggable 3P · MX15EDGRM-3.5-03P-GN01-Cu-A · C5188342

| Pin | Name | Net |
|---|---|---|
| 1 | DQ | `ONEWIRE_BUS` |
| 2 | VDD | `+3V3` |
| 3 | GND | `GND` |

**J305** DS18B20 · 3.5 mm pluggable 3P · MX15EDGRM-3.5-03P-GN01-Cu-A · C5188342

| Pin | Name | Net |
|---|---|---|
| 1 | DQ | `ONEWIRE_BUS` |
| 2 | VDD | `+3V3` |
| 3 | GND | `GND` |

**J306** DS18B20 · 3.5 mm pluggable 3P · MX15EDGRM-3.5-03P-GN01-Cu-A · C5188342

| Pin | Name | Net |
|---|---|---|
| 1 | DQ | `ONEWIRE_BUS` |
| 2 | VDD | `+3V3` |
| 3 | GND | `GND` |

**Two-terminal parts and test points**

| Ref | Value | Package | Part · LCSC | Connection | Note |
|---|---|---|---|---|---|
| C301 | 100nF | 0603 |  | `VSTR_DIV` – `GND` | X7R ≥ 10 V |
| F301 | 1A fast | 1206 | 0466001.NRHF · C151135 | `T0` – `T0_F` |  |
| F302 | 1A fast | 1206 | 0466001.NRHF · C151135 | `T1` – `T1_F` |  |
| F303 | 1A fast | 1206 | 0466001.NRHF · C151135 | `T2` – `T2_F` |  |
| F304 | 1A fast | 1206 | 0466001.NRHF · C151135 | `T3` – `T3_F` |  |
| F305 | 1A fast | 1206 | 0466001.NRHF · C151135 | `T4` – `T4_F` |  |
| F306 | 1A fast | 1206 | 0466001.NRHF · C151135 | `T5` – `T5_F` |  |
| F307 | 1A fast | 1206 | 0466001.NRHF · C151135 | `T6` – `T6_F` |  |
| F308 | 1A fast | 1206 | 0466001.NRHF · C151135 | `T7` – `T7_F` |  |
| F309 | 1A fast | 1206 | 0466001.NRHF · C151135 | `T8` – `T8_F` |  |
| F310 | 1A fast | 1206 | 0466001.NRHF · C151135 | `T9` – `T9_F` |  |
| F311 | 1A fast | 1206 | 0466001.NRHF · C151135 | `T10` – `T10_F` |  |
| F312 | 1A fast | 1206 | 0466001.NRHF · C151135 | `T11` – `T11_F` |  |
| F313 | 1A fast | 1206 | 0466001.NRHF · C151135 | `T12` – `T12_F` |  |
| F314 | 1A fast | 1206 | 0466001.NRHF · C151135 | `T13` – `T13_F` |  |
| F315 | 1A fast | 1206 | 0466001.NRHF · C151135 | `T14` – `T14_F` |  |
| F316 | 1A fast | 1206 | 0466001.NRHF · C151135 | `T15` – `T15_F` |  |
| F317 | 1A fast | 1206 | 0466001.NRHF · C151135 | `T16` – `T16_F` |  |
| R301 | 1k | 1206 | 1206W4F1001T5E · C4410 | `T0_F` – `T0_M` | pulse-proof (anti-surge) |
| R302 | 1k | 1206 | 1206W4F1001T5E · C4410 | `T1_F` – `T1_M` | pulse-proof (anti-surge) |
| R303 | 1k | 1206 | 1206W4F1001T5E · C4410 | `T2_F` – `T2_M` | pulse-proof (anti-surge) |
| R304 | 1k | 1206 | 1206W4F1001T5E · C4410 | `T3_F` – `T3_M` | pulse-proof (anti-surge) |
| R305 | 1k | 1206 | 1206W4F1001T5E · C4410 | `T4_F` – `T4_M` | pulse-proof (anti-surge) |
| R306 | 1k | 1206 | 1206W4F1001T5E · C4410 | `T5_F` – `T5_M` | pulse-proof (anti-surge) |
| R307 | 1k | 1206 | 1206W4F1001T5E · C4410 | `T6_F` – `T6_M` | pulse-proof (anti-surge) |
| R308 | 1k | 1206 | 1206W4F1001T5E · C4410 | `T7_F` – `T7_M` | pulse-proof (anti-surge) |
| R309 | 1k | 1206 | 1206W4F1001T5E · C4410 | `T8_F` – `T8_M` | pulse-proof (anti-surge) |
| R310 | 1k | 1206 | 1206W4F1001T5E · C4410 | `T9_F` – `T9_M` | pulse-proof (anti-surge) |
| R311 | 1k | 1206 | 1206W4F1001T5E · C4410 | `T10_F` – `T10_M` | pulse-proof (anti-surge) |
| R312 | 1k | 1206 | 1206W4F1001T5E · C4410 | `T11_F` – `T11_M` | pulse-proof (anti-surge) |
| R313 | 1k | 1206 | 1206W4F1001T5E · C4410 | `T12_F` – `T12_M` | pulse-proof (anti-surge) |
| R314 | 1k | 1206 | 1206W4F1001T5E · C4410 | `T13_F` – `T13_M` | pulse-proof (anti-surge) |
| R315 | 1k | 1206 | 1206W4F1001T5E · C4410 | `T14_F` – `T14_M` | pulse-proof (anti-surge) |
| R316 | 1k | 1206 | 1206W4F1001T5E · C4410 | `T15_F` – `T15_M` | pulse-proof (anti-surge) |
| R317 | 1k | 1206 | 1206W4F1001T5E · C4410 | `T16_F` – `T16_M` | pulse-proof (anti-surge) |
| R318 | 510k | 0805 | 0805W8F5103T5E · C17733 | `T16_F` – `VSTR_A` |  |
| R319 | 510k | 0805 | 0805W8F5103T5E · C17733 | `VSTR_A` – `VSTR_B` |  |
| R320 | 510k | 0805 | 0805W8F5103T5E · C17733 | `VSTR_B` – `VSTR_DIV` |  |
| R321 | 100k | 0603 | RT0603BRD07100KL (0.1 %, 25 ppm/K) · C122538 | `VSTR_DIV` – `GND` | 0.1% |
| R322 | 100 | 0603 |  | `ACT_BAL_EN` – `ACT_BAL_EN_OUT` |  |
| R323 | 100 | 0603 |  | `ACT_BAL_PWM` – `ACT_BAL_PWM_OUT` |  |
| R324 | 100 | 0603 |  | `ONEWIRE` – `ONEWIRE_BUS` |  |
| TP301 | VSTR_DIV | – |  | `VSTR_DIV` |  |

---

## 8. Sheet MEAS_MUX (400)

- **Tap switches K401…K417** (AQY280S, 350 V): output between `Tj_M` and the bus (even taps → `BUS_A`,
  odd taps → `BUS_B`). LED anode via 560 Ω from +5V, LED cathode to the decoder:
  - T0 (K401) and T16 (K417): directly to U401 output `SEL0_n` / `SEL15_n`;
  - T1…T15 (K402…K416): through a BAT54A (D401…D415, common anode = LED cathode) to the two outputs
    `SEL(j−1)_n` and `SELj_n`.
  - **Cell k is selected by output `SEL(k−1)_n`**: it turns on exactly taps k−1 and k (one on each bus).
    No firmware error can put two cells or a non-adjacent pair across the capacitor.
- **Flying capacitor C402**: 470 nF polypropylene film between `BUS_A` and `BUS_B`; nothing else on the buses.
- **Transfer H-bridge K418…K421** (decoder U402, enabled only while `TAP_EN_n` is high = all taps off):

  | Switch | Output | LED cathode | On for |
  |---|---|---|---|
  | K418 (A_P) | BUS_A → FC_HI | `XY0_n` | even cell |
  | K419 (B_P) | BUS_B → FC_HI | `XY1_n` | odd cell |
  | K420 (A_G) | BUS_A → FC_GND | D416 → `XY1_n`, `XY2_n` | odd cell, discharge |
  | K421 (B_G) | BUS_B → FC_GND | D417 → `XY0_n`, `XY2_n` | even cell, discharge |

  U402 inputs: A = POL (1 = odd cell), B = DISCH; outputs Y0 = even cell, Y1 = odd cell, Y2 = discharge.
- LED current ≈ (5 V − 1.3 V − 0.35 V − 0.4 V) / 560 Ω ≈ 5 mA (AQY280S operate current ≤ 3 mA).

**U401** 74HCT154 · SOIC-24 · CD74HCT154M96 · C2653299

| Pin | Name | Net |
|---|---|---|
| 1 | Y0 | `SEL0_n` |
| 2 | Y1 | `SEL1_n` |
| 3 | Y2 | `SEL2_n` |
| 4 | Y3 | `SEL3_n` |
| 5 | Y4 | `SEL4_n` |
| 6 | Y5 | `SEL5_n` |
| 7 | Y6 | `SEL6_n` |
| 8 | Y7 | `SEL7_n` |
| 9 | Y8 | `SEL8_n` |
| 10 | Y9 | `SEL9_n` |
| 11 | Y10 | `SEL10_n` |
| 12 | GND | `GND` |
| 13 | Y11 | `SEL11_n` |
| 14 | Y12 | `SEL12_n` |
| 15 | Y13 | `SEL13_n` |
| 16 | Y14 | `SEL14_n` |
| 17 | Y15 | `SEL15_n` |
| 18 | G1 | `TAP_EN_n` |
| 19 | G2 | `GND` |
| 20 | D | `CELL_A3` |
| 21 | C | `CELL_A2` |
| 22 | B | `CELL_A1` |
| 23 | A | `CELL_A0` |
| 24 | VCC | `+5V` |

**U402** 74HCT138 · SO-16 · 74HCT138D · C56242452

| Pin | Name | Net |
|---|---|---|
| 1 | A | `POL` |
| 2 | B | `DISCH` |
| 3 | C | `GND` |
| 4 | G2A | `XFER_n` |
| 5 | G2B | `GND` |
| 6 | G1 | `TAP_EN_n` |
| 7 | Y7 | nc |
| 8 | GND | `GND` |
| 9 | Y6 | nc |
| 10 | Y5 | nc |
| 11 | Y4 | nc |
| 12 | Y3 | nc |
| 13 | Y2 | `XY2_n` |
| 14 | Y1 | `XY1_n` |
| 15 | Y0 | `XY0_n` |
| 16 | VCC | `+5V` |

**PhotoMOS relays** (AQY280SX · C425101, SOP-4)

| Ref | LED A (1) | LED K (2) | out (3) | out (4) |
|---|---|---|---|---|
| K401 | `K401_LED` | `SEL0_n` | `BUS_A` | `T0_M` |
| K402 | `K402_LED` | `TAPK1` | `BUS_B` | `T1_M` |
| K403 | `K403_LED` | `TAPK2` | `BUS_A` | `T2_M` |
| K404 | `K404_LED` | `TAPK3` | `BUS_B` | `T3_M` |
| K405 | `K405_LED` | `TAPK4` | `BUS_A` | `T4_M` |
| K406 | `K406_LED` | `TAPK5` | `BUS_B` | `T5_M` |
| K407 | `K407_LED` | `TAPK6` | `BUS_A` | `T6_M` |
| K408 | `K408_LED` | `TAPK7` | `BUS_B` | `T7_M` |
| K409 | `K409_LED` | `TAPK8` | `BUS_A` | `T8_M` |
| K410 | `K410_LED` | `TAPK9` | `BUS_B` | `T9_M` |
| K411 | `K411_LED` | `TAPK10` | `BUS_A` | `T10_M` |
| K412 | `K412_LED` | `TAPK11` | `BUS_B` | `T11_M` |
| K413 | `K413_LED` | `TAPK12` | `BUS_A` | `T12_M` |
| K414 | `K414_LED` | `TAPK13` | `BUS_B` | `T13_M` |
| K415 | `K415_LED` | `TAPK14` | `BUS_A` | `T14_M` |
| K416 | `K416_LED` | `TAPK15` | `BUS_B` | `T15_M` |
| K417 | `K417_LED` | `SEL15_n` | `BUS_A` | `T16_M` |
| K418 | `K418_LED` | `XY0_n` | `FC_HI` | `BUS_A` |
| K419 | `K419_LED` | `XY1_n` | `FC_HI` | `BUS_B` |
| K420 | `K420_LED` | `XK_AG` | `FC_GND` | `BUS_A` |
| K421 | `K421_LED` | `XK_BG` | `FC_GND` | `BUS_B` |

**Diode-OR** (BAT54ALT1G · C92068, SOT-23, common anode)

| Ref | K1 (1) | K2 (2) | A (3) |
|---|---|---|---|
| D401 | `SEL0_n` | `SEL1_n` | `TAPK1` |
| D402 | `SEL1_n` | `SEL2_n` | `TAPK2` |
| D403 | `SEL2_n` | `SEL3_n` | `TAPK3` |
| D404 | `SEL3_n` | `SEL4_n` | `TAPK4` |
| D405 | `SEL4_n` | `SEL5_n` | `TAPK5` |
| D406 | `SEL5_n` | `SEL6_n` | `TAPK6` |
| D407 | `SEL6_n` | `SEL7_n` | `TAPK7` |
| D408 | `SEL7_n` | `SEL8_n` | `TAPK8` |
| D409 | `SEL8_n` | `SEL9_n` | `TAPK9` |
| D410 | `SEL9_n` | `SEL10_n` | `TAPK10` |
| D411 | `SEL10_n` | `SEL11_n` | `TAPK11` |
| D412 | `SEL11_n` | `SEL12_n` | `TAPK12` |
| D413 | `SEL12_n` | `SEL13_n` | `TAPK13` |
| D414 | `SEL13_n` | `SEL14_n` | `TAPK14` |
| D415 | `SEL14_n` | `SEL15_n` | `TAPK15` |
| D416 | `XY1_n` | `XY2_n` | `XK_AG` |
| D417 | `XY0_n` | `XY2_n` | `XK_BG` |

**Two-terminal parts and test points**

| Ref | Value | Package | Part · LCSC | Connection | Note |
|---|---|---|---|---|---|
| C401 | 100nF | 0603 |  | `+5V` – `GND` | X7R/X5R ≥ 10 V |
| C402 | 470nF PP film | THT, pitch 10 mm | ECWFD2W474Q1 · C178474 | `BUS_A` – `BUS_B` | polypropylene, no ceramic |
| C403 | 100nF | 0603 |  | `+5V` – `GND` | X7R/X5R ≥ 10 V |
| R401 | 560 | 0603 |  | `+5V` – `K401_LED` |  |
| R402 | 560 | 0603 |  | `+5V` – `K402_LED` |  |
| R403 | 560 | 0603 |  | `+5V` – `K403_LED` |  |
| R404 | 560 | 0603 |  | `+5V` – `K404_LED` |  |
| R405 | 560 | 0603 |  | `+5V` – `K405_LED` |  |
| R406 | 560 | 0603 |  | `+5V` – `K406_LED` |  |
| R407 | 560 | 0603 |  | `+5V` – `K407_LED` |  |
| R408 | 560 | 0603 |  | `+5V` – `K408_LED` |  |
| R409 | 560 | 0603 |  | `+5V` – `K409_LED` |  |
| R410 | 560 | 0603 |  | `+5V` – `K410_LED` |  |
| R411 | 560 | 0603 |  | `+5V` – `K411_LED` |  |
| R412 | 560 | 0603 |  | `+5V` – `K412_LED` |  |
| R413 | 560 | 0603 |  | `+5V` – `K413_LED` |  |
| R414 | 560 | 0603 |  | `+5V` – `K414_LED` |  |
| R415 | 560 | 0603 |  | `+5V` – `K415_LED` |  |
| R416 | 560 | 0603 |  | `+5V` – `K416_LED` |  |
| R417 | 560 | 0603 |  | `+5V` – `K417_LED` |  |
| R418 | 560 | 0603 |  | `+5V` – `K418_LED` |  |
| R419 | 560 | 0603 |  | `+5V` – `K419_LED` |  |
| R420 | 560 | 0603 |  | `+5V` – `K420_LED` |  |
| R421 | 560 | 0603 |  | `+5V` – `K421_LED` |  |

---

## 9. Sheet ADC (500)

- `FC_HI` → R501 10 kΩ → OPA333 unity-gain buffer → R502 100 Ω / C502 10 nF C0G → ADS1220 AIN0.
- `FC_GND` → R503 100 Ω / C503 → AIN1, and to GND **only** through R504 (0 Ω) at the ADC (star point).
- ADS1220: AIN0−AIN1 = cell voltage, AIN2 = `VSTR_DIV`, AIN3 = `NTC_DIV`; reference REFP0/REFN0 = REF5045
  (4.5 V), AVDD = +5VA, DVDD = +3V3 (3.3 V logic). Configuration: PGA bypassed, gain 1, single shot, 330 SPS.
- REF5045 needs V<sub>IN</sub> ≥ 4.7 V: with USB power only (+5V ≈ 4.6 V after D103) the reference is not in
  regulation – USB-only operation is for flashing and tests without measurement (SHW-044).

**U501** OPA333AIDBV · SOT-23-5 · OPA333AIDBVR · C30878

| Pin | Name | Net |
|---|---|---|
| 1 | OUT | `BUF_OUT` |
| 2 | V− | `GND` |
| 3 | +IN | `BUF_IN` |
| 4 | −IN | `BUF_OUT` |
| 5 | V+ | `+5VA` |

**U502** ADS1220IPW · TSSOP-16 · ADS1220IPWR · C48263

| Pin | Name | Net |
|---|---|---|
| 1 | SCLK | `ADC_SCLK` |
| 2 | CS | `ADC_CS` |
| 3 | CLK | `GND` |
| 4 | DGND | `GND` |
| 5 | AVSS | `GND` |
| 6 | AIN3/REFN1 | `NTC_DIV` |
| 7 | AIN2 | `VSTR_DIV` |
| 8 | REFN0 | `GND` |
| 9 | REFP0 | `VREF` |
| 10 | AIN1 | `AIN1_F` |
| 11 | AIN0/REFP1 | `AIN0_F` |
| 12 | AVDD | `+5VA` |
| 13 | DVDD | `+3V3` |
| 14 | DRDY | `ADC_DRDY` |
| 15 | DOUT/DRDY | `ADC_DOUT` |
| 16 | DIN | `ADC_DIN` |

**U503** REF5045AIDR · SOIC-8 · REF5045AIDR · C181339

| Pin | Name | Net |
|---|---|---|
| 1 | DNC | nc |
| 2 | VIN | `+5VA` |
| 3 | TEMP | nc |
| 4 | GND | `GND` |
| 5 | TRIM/NR | `VREF_NR` |
| 6 | VOUT | `VREF` |
| 7 | NC | nc |
| 8 | DNC | nc |

**Two-terminal parts and test points**

| Ref | Value | Package | Part · LCSC | Connection | Note |
|---|---|---|---|---|---|
| C501 | 100nF | 0603 |  | `+5VA` – `GND` | X7R/X5R ≥ 10 V |
| C502 | 10nF | 0603 |  | `AIN0_F` – `GND` | C0G |
| C503 | 10nF | 0603 |  | `AIN1_F` – `GND` | C0G |
| C504 | 1uF | 0603 |  | `+5VA` – `GND` | X7R/X5R ≥ 10 V |
| C505 | 100nF | 0603 |  | `+5VA` – `GND` | X7R/X5R ≥ 10 V |
| C506 | 100nF | 0603 |  | `+3V3` – `GND` | X7R ≥ 10 V |
| C507 | 1uF | 0603 |  | `VREF_NR` – `GND` | X7R/X5R ≥ 10 V |
| C508 | 1uF | 0603 |  | `+5VA` – `GND` | X7R/X5R ≥ 10 V |
| C509 | 10uF | 0805 |  | `VREF` – `GND` | X7R/X5R ≥ 10 V |
| C510 | 100nF | 0805 |  | `VREF` – `GND` | X7R/X5R ≥ 10 V |
| R501 | 10k | 0603 |  | `FC_HI` – `BUF_IN` |  |
| R502 | 100 | 0603 |  | `BUF_OUT` – `AIN0_F` |  |
| R503 | 100 | 0603 |  | `FC_GND` – `AIN1_F` |  |
| R504 | 0R | 0603 |  | `FC_GND` – `GND` | star point FC_GND – GND, place at the ADC |
| TP501 | VREF | – |  | `VREF` |  |
| TP502 | FC_HI | – |  | `FC_HI` |  |
| TP503 | BUF_OUT | – |  | `BUF_OUT` |  |

---

## 10. Sheet BALANCING (600)

- U601 PCA9685 at I²C address 0x40 (A0…A5 = GND), supply +3V3, `OE` = `BAL_OE_n` (pull-up on the MCU sheet:
  all outputs low while the ESP32 is in reset, crashed or asleep).
- Per channel n = 1…16 (cell n between `T(n−1)_F` and `Tn_F`): output `BAL_DRVn` → 390 Ω → AQY282 LED
  (cathode GND); optional indicator LED with 1 kΩ; AQY282 output `T(n−1)_F` ↔ `BAL_Rn`; 2 × 33 Ω 2512 1 W
  in parallel `BAL_Rn` ↔ `Tn_F` → ≈ 200 mA at 3.3 V (0.4 W per resistor, 40 % of rating).
- Indicator LEDs D601…D616 (optional): red, V<sub>F</sub> ≈ 2 V → ≈ 1.3 mA from the 3.3 V PCA9685 output.
- RT601 NTC between the bleed resistors (place in the middle of the resistor field), divider R665 10 kΩ
  0.1 % from VREF → `NTC_DIV` (ratiometric).

**U601** PCA9685PW · TSSOP-28 · PCA9685PW,118 · C2678753

| Pin | Name | Net |
|---|---|---|
| 1 | A0 | `GND` |
| 2 | A1 | `GND` |
| 3 | A2 | `GND` |
| 4 | A3 | `GND` |
| 5 | A4 | `GND` |
| 6 | LED0 | `BAL_DRV1` |
| 7 | LED1 | `BAL_DRV2` |
| 8 | LED2 | `BAL_DRV3` |
| 9 | LED3 | `BAL_DRV4` |
| 10 | LED4 | `BAL_DRV5` |
| 11 | LED5 | `BAL_DRV6` |
| 12 | LED6 | `BAL_DRV7` |
| 13 | LED7 | `BAL_DRV8` |
| 14 | VSS | `GND` |
| 15 | LED8 | `BAL_DRV9` |
| 16 | LED9 | `BAL_DRV10` |
| 17 | LED10 | `BAL_DRV11` |
| 18 | LED11 | `BAL_DRV12` |
| 19 | LED12 | `BAL_DRV13` |
| 20 | LED13 | `BAL_DRV14` |
| 21 | LED14 | `BAL_DRV15` |
| 22 | LED15 | `BAL_DRV16` |
| 23 | OE | `BAL_OE_n` |
| 24 | A5 | `GND` |
| 25 | EXTCLK | `GND` |
| 26 | SCL | `I2C_SCL` |
| 27 | SDA | `I2C_SDA` |
| 28 | VDD | `+3V3` |

**PhotoMOS relays** (AQY282SX · C250827, SOP-4)

| Ref | LED A (1) | LED K (2) | out (3) | out (4) |
|---|---|---|---|---|
| K601 | `K601_LED` | `GND` | `BAL_R1` | `T0_F` |
| K602 | `K602_LED` | `GND` | `BAL_R2` | `T1_F` |
| K603 | `K603_LED` | `GND` | `BAL_R3` | `T2_F` |
| K604 | `K604_LED` | `GND` | `BAL_R4` | `T3_F` |
| K605 | `K605_LED` | `GND` | `BAL_R5` | `T4_F` |
| K606 | `K606_LED` | `GND` | `BAL_R6` | `T5_F` |
| K607 | `K607_LED` | `GND` | `BAL_R7` | `T6_F` |
| K608 | `K608_LED` | `GND` | `BAL_R8` | `T7_F` |
| K609 | `K609_LED` | `GND` | `BAL_R9` | `T8_F` |
| K610 | `K610_LED` | `GND` | `BAL_R10` | `T9_F` |
| K611 | `K611_LED` | `GND` | `BAL_R11` | `T10_F` |
| K612 | `K612_LED` | `GND` | `BAL_R12` | `T11_F` |
| K613 | `K613_LED` | `GND` | `BAL_R13` | `T12_F` |
| K614 | `K614_LED` | `GND` | `BAL_R14` | `T13_F` |
| K615 | `K615_LED` | `GND` | `BAL_R15` | `T14_F` |
| K616 | `K616_LED` | `GND` | `BAL_R16` | `T15_F` |

**Two-terminal parts and test points**

| Ref | Value | Package | Part · LCSC | Connection | Note |
|---|---|---|---|---|---|
| C601 | 10uF | 0603 |  | `+3V3` – `GND` | X7R ≥ 10 V |
| C602 | 100nF | 0603 |  | `+3V3` – `GND` | X7R ≥ 10 V |
| C603 | 100nF | 0603 |  | `NTC_DIV` – `GND` | X7R ≥ 10 V |
| D601 | red | 0603 | KT-0603R · C2286 | K: `GND` · A: `D601_A` | optional indicator |
| D602 | red | 0603 | KT-0603R · C2286 | K: `GND` · A: `D602_A` | optional indicator |
| D603 | red | 0603 | KT-0603R · C2286 | K: `GND` · A: `D603_A` | optional indicator |
| D604 | red | 0603 | KT-0603R · C2286 | K: `GND` · A: `D604_A` | optional indicator |
| D605 | red | 0603 | KT-0603R · C2286 | K: `GND` · A: `D605_A` | optional indicator |
| D606 | red | 0603 | KT-0603R · C2286 | K: `GND` · A: `D606_A` | optional indicator |
| D607 | red | 0603 | KT-0603R · C2286 | K: `GND` · A: `D607_A` | optional indicator |
| D608 | red | 0603 | KT-0603R · C2286 | K: `GND` · A: `D608_A` | optional indicator |
| D609 | red | 0603 | KT-0603R · C2286 | K: `GND` · A: `D609_A` | optional indicator |
| D610 | red | 0603 | KT-0603R · C2286 | K: `GND` · A: `D610_A` | optional indicator |
| D611 | red | 0603 | KT-0603R · C2286 | K: `GND` · A: `D611_A` | optional indicator |
| D612 | red | 0603 | KT-0603R · C2286 | K: `GND` · A: `D612_A` | optional indicator |
| D613 | red | 0603 | KT-0603R · C2286 | K: `GND` · A: `D613_A` | optional indicator |
| D614 | red | 0603 | KT-0603R · C2286 | K: `GND` · A: `D614_A` | optional indicator |
| D615 | red | 0603 | KT-0603R · C2286 | K: `GND` · A: `D615_A` | optional indicator |
| D616 | red | 0603 | KT-0603R · C2286 | K: `GND` · A: `D616_A` | optional indicator |
| R601 | 390 | 0603 |  | `BAL_DRV1` – `K601_LED` |  |
| R602 | 1k | 0603 |  | `BAL_DRV1` – `D601_A` |  |
| R603 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R1` – `T1_F` | 1 W |
| R604 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R1` – `T1_F` | 1 W |
| R605 | 390 | 0603 |  | `BAL_DRV2` – `K602_LED` |  |
| R606 | 1k | 0603 |  | `BAL_DRV2` – `D602_A` |  |
| R607 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R2` – `T2_F` | 1 W |
| R608 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R2` – `T2_F` | 1 W |
| R609 | 390 | 0603 |  | `BAL_DRV3` – `K603_LED` |  |
| R610 | 1k | 0603 |  | `BAL_DRV3` – `D603_A` |  |
| R611 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R3` – `T3_F` | 1 W |
| R612 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R3` – `T3_F` | 1 W |
| R613 | 390 | 0603 |  | `BAL_DRV4` – `K604_LED` |  |
| R614 | 1k | 0603 |  | `BAL_DRV4` – `D604_A` |  |
| R615 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R4` – `T4_F` | 1 W |
| R616 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R4` – `T4_F` | 1 W |
| R617 | 390 | 0603 |  | `BAL_DRV5` – `K605_LED` |  |
| R618 | 1k | 0603 |  | `BAL_DRV5` – `D605_A` |  |
| R619 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R5` – `T5_F` | 1 W |
| R620 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R5` – `T5_F` | 1 W |
| R621 | 390 | 0603 |  | `BAL_DRV6` – `K606_LED` |  |
| R622 | 1k | 0603 |  | `BAL_DRV6` – `D606_A` |  |
| R623 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R6` – `T6_F` | 1 W |
| R624 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R6` – `T6_F` | 1 W |
| R625 | 390 | 0603 |  | `BAL_DRV7` – `K607_LED` |  |
| R626 | 1k | 0603 |  | `BAL_DRV7` – `D607_A` |  |
| R627 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R7` – `T7_F` | 1 W |
| R628 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R7` – `T7_F` | 1 W |
| R629 | 390 | 0603 |  | `BAL_DRV8` – `K608_LED` |  |
| R630 | 1k | 0603 |  | `BAL_DRV8` – `D608_A` |  |
| R631 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R8` – `T8_F` | 1 W |
| R632 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R8` – `T8_F` | 1 W |
| R633 | 390 | 0603 |  | `BAL_DRV9` – `K609_LED` |  |
| R634 | 1k | 0603 |  | `BAL_DRV9` – `D609_A` |  |
| R635 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R9` – `T9_F` | 1 W |
| R636 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R9` – `T9_F` | 1 W |
| R637 | 390 | 0603 |  | `BAL_DRV10` – `K610_LED` |  |
| R638 | 1k | 0603 |  | `BAL_DRV10` – `D610_A` |  |
| R639 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R10` – `T10_F` | 1 W |
| R640 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R10` – `T10_F` | 1 W |
| R641 | 390 | 0603 |  | `BAL_DRV11` – `K611_LED` |  |
| R642 | 1k | 0603 |  | `BAL_DRV11` – `D611_A` |  |
| R643 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R11` – `T11_F` | 1 W |
| R644 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R11` – `T11_F` | 1 W |
| R645 | 390 | 0603 |  | `BAL_DRV12` – `K612_LED` |  |
| R646 | 1k | 0603 |  | `BAL_DRV12` – `D612_A` |  |
| R647 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R12` – `T12_F` | 1 W |
| R648 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R12` – `T12_F` | 1 W |
| R649 | 390 | 0603 |  | `BAL_DRV13` – `K613_LED` |  |
| R650 | 1k | 0603 |  | `BAL_DRV13` – `D613_A` |  |
| R651 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R13` – `T13_F` | 1 W |
| R652 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R13` – `T13_F` | 1 W |
| R653 | 390 | 0603 |  | `BAL_DRV14` – `K614_LED` |  |
| R654 | 1k | 0603 |  | `BAL_DRV14` – `D614_A` |  |
| R655 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R14` – `T14_F` | 1 W |
| R656 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R14` – `T14_F` | 1 W |
| R657 | 390 | 0603 |  | `BAL_DRV15` – `K615_LED` |  |
| R658 | 1k | 0603 |  | `BAL_DRV15` – `D615_A` |  |
| R659 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R15` – `T15_F` | 1 W |
| R660 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R15` – `T15_F` | 1 W |
| R661 | 390 | 0603 |  | `BAL_DRV16` – `K616_LED` |  |
| R662 | 1k | 0603 |  | `BAL_DRV16` – `D616_A` |  |
| R663 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R16` – `T16_F` | 1 W |
| R664 | 33 | 2512 | 25121WF330JT4E (1 W) · C53728 | `BAL_R16` – `T16_F` | 1 W |
| R665 | 10k | 0603 | RT0603BRD0710KL (0.1 %, 25 ppm/K) · C95204 | `VREF` – `NTC_DIV` | 0.1% |
| RT601 | 10k NTC B3434 | 0603 | NCP18XH103F03RB · C13564 | `NTC_DIV` – `GND` | between the bleed resistors |

---

## 11. Mechanical

| Ref | Value | Note |
|---|---|---|
| SCREW1 | M4 plated | nylon screws/spacers only, insulating enclosure (SHW-060/061) |
| SCREW2 | M4 plated | nylon screws/spacers only, insulating enclosure (SHW-060/061) |
| SCREW3 | M4 plated | nylon screws/spacers only, insulating enclosure (SHW-060/061) |
| SCREW4 | M4 plated | nylon screws/spacers only, insulating enclosure (SHW-060/061) |

Mounting holes (decision review 1): plated M4 holes, **mounted with nylon screws and spacers in an insulating
enclosure**; the reinforced insulation (≥ 600 V working voltage to the enclosure, SHW-060/061) is provided by the
insulating mounting. Never use metal screws. Antenna keep-out of the ESP32 module at the board edge.

---

## 12. Calculations

### 12.1 Low-power state (SHW-045: ≤ 1 mA from the module)

Firmware puts the PCA9685 into SLEEP, the ADS1220 into power-down, and the ESP32 into deep sleep; the pull-ups
keep taps, transfer and balancing off. Worst case address: 3 bits set (addresses 1…10, e.g. 7).

| Load (current on the 5 V rail; 3.3 V loads pass through the LDO) | Current |
|---|---|
| REF5045 (always on, 1 mA max) | 1.0 mA |
| ESP32-S3 module deep sleep (estimate incl. PSRAM) | ≤ 0.1 mA |
| TLV75733 + OPA333 + 2 × 74HCT + PCA9685 sleep + 4 × DS18B20 standby | ≈ 0.06 mA |
| Address pull-downs (3 × 100 kΩ at 3.3 V) | 0.1 mA |
| Address LEDs (3 × red/green with 4.7 kΩ, ≈ 0.28 mA each) | 0.84 mA |
| **Sum on the 5 V rail** | **≈ 2.1 mA = 10.5 mW** |
| LM5164-Q1 (efficiency ≈ 60 % at light load, I<sub>Q</sub> 10.5 µA) → from the module at 40 V (16 × 2.5 V) | **0.44 mA** |
| + module divider (36 µA) + UVLO divider (≤ 24 µA) | **≈ 0.50 mA** |
| + wake-up every 10 min (≈ 2 s at 0.5 W, averaged) | **≈ 0.54 mA ≤ 1 mA** ✓ |

The address LEDs make the consumption depend on the address: 2 bits more = 0.56 mA at 3.3 V ≈ 0.05 mA from the
module – well inside the 1 mA equality of SHW-043. With 1 kΩ they would draw ≈ 1.3 mA each and the budget would
reach ≈ 0.9 mA, too close to the limit.

### 12.2 Scan time (SHW-005: ≤ 0.5 s)

τ = (2 × 1 kΩ + 2 × R<sub>on</sub>) × 470 nF ≈ 0.96 ms; charging 12 τ ≈ 12 ms (< 0.1 mV residual).
Per cell: discharge 1 ms + wait 1 ms + charge 12 ms + taps off 1 ms + transfer/settle 2 ms + conversion
3.1 ms ≈ 20 ms → 16 cells ≈ 0.32 s, plus 5 ms settling after balancing off and two conversions for module
voltage and NTC → **≈ 0.34 s** ✓.

### 12.3 Accuracy (SHW-002: ±2 mV)

| Source | Error |
|---|---|
| REF5045 drift (A grade 3 ppm/K, ±15 K from calibration) | ≤ 0.2 mV |
| ADS1220 noise at 330 SPS (averaged), INL | < 0.1 mV |
| OPA333 offset (zero drift) | < 0.01 mV |
| Charging residual (12 τ) | < 0.1 mV |
| PhotoMOS leakage during transfer (nA × ms / 470 nF) | < 0.05 mV |
| Charge sharing with the switch output capacitances (different common-mode voltage per cell) | up to ≈ 1 mV, constant per channel → removed by the per-channel calibration (SWS-042) |
| **Total after per-channel calibration** | **≈ 0.5 mV typ., ≤ 1.2 mV worst case** ✓ |

Dielectric absorption: cells are read odd first, then even, so the capacitor keeps its polarity, and
consecutive cells differ by only tens of millivolts.

### 12.4 Balancing heat (SHW-021)

All 16 channels at 3.65 V: 16 × 0.81 W ≈ 13 W. Spread the 32 resistors over the board edge with copper
pours; the firmware stops balancing above `t_board_max` (NTC RT601 and ADS1220 die temperature). The
average balancing current is reduced by the scan pause (≈ 0.34 s per `meas_period`).

---

## 13. Layout rules (for W-08)

1. Net classes `HV`/`BAL` (taps, buses, module voltage, bleed nets): clearance 0.6 mm (IPC-2221 B2, ≤ 150 V),
   ≥ 1 mm between tap traces wherever possible.
2. Measurement matrix, C402, buffer and ADC in one compact area with a GND guard ring around
   BUS_A/BUS_B/C402/BUF_IN.
3. Star ground at R504: FC_GND, ADC AVSS/REFN0, REF5045 GND. The buck current loop and the J101 return
   must not flow through it.
4. Balancing current only on the `Tj_F` → AQY282 → 33 Ω path, never through the 1 kΩ / matrix path.
5. Bleed resistors along the board edge with copper pours, NTC in between.
6. Buck converter away from the ADC, small switching loop, R106/C113 close to SW, C114 close to FB.
7. ESP32 antenna keep-out at the board edge; mounting holes per section 11.
8. Test points: VIN_HV, +5V, +5VA, +3V3, GND, PGOOD, VREF, FC_HI, BUF_OUT, VSTR_DIV, TXD0/RXD0.

---

## 14. Measurement sequence (firmware)

Balancing paused (`BAL_OE_n` = 1, `ACT_BAL_EN` = 0), wait 5 ms. Odd cells first, then even cells. For cell k:

1. `XFER_n` = 1, POL = 0, DISCH = 1, `XFER_n` = 0 → C402 discharged (1 ms), `XFER_n` = 1, wait 1 ms.
2. `CELL_A` = k − 1, `TAP_EN_n` = 0 → C402 charges to cell k (12 ms).
3. `TAP_EN_n` = 1, wait 1 ms.
4. POL = k & 1, DISCH = 0, `XFER_n` = 0, wait 2 ms.
5. ADS1220 single shot AIN0−AIN1 → V<sub>cell</sub>.
6. `XFER_n` = 1.

Diagnostics: open tap wire (reads ≈ 0 V), stuck tap switch (discharge, transfer without charging → must read
≈ 0 V), sum of cells vs. AIN2 (`plaus_tol`), system offset (discharge state through the buffer).

---

## 15. Check before ordering

- [x] Schematic drawn in EasyEDA; netlist compared with [slave_4_0_netlist.csv](slave_4_0_netlist.csv):
      `python tools/check_easyeda_netlist.py hw/slave/slave_4_0.epro2 hw/slave/slave_4_0_netlist.csv`
      (needs "Update PCB from schematic" first; reviews: [1](slave_4_0_review_1.md)) – no differences on 2026-11-24
- [ ] L101: saturation current ≥ 1.8 A in the datasheet of the chosen part
- [ ] C402 footprint: THT, 10 mm pitch (ECWFD2W474Q1)
- [ ] REF5045AIDR stock (38 + 63 pcs at the time of writing) – order early
- [ ] AQY280S off-state leakage and LED current (≤ 3 mA) in the datasheet
- [ ] Prototype first with 4 cells and a bench supply
