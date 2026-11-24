# Slave 4.0 – Schematic review 1 (first EasyEDA draft)

| | |
|---|---|
| Reviewed | `hw/slave/slave_4_0.epro2` (2026-11-24, EasyEDA Pro 3.2.209), 6 pages, 314 parts |
| Against | [slave_4_0_schematic.md](slave_4_0_schematic.md) / [slave_4_0_netlist.csv](slave_4_0_netlist.csv) |
| Method | `python tools/check_easyeda_netlist.py hw/slave/slave_4_0.epro2 hw/slave/slave_4_0_netlist.csv` (pad nets of the PCB document, which matches the schematic: same 314 designators), plus manual check of the differences |

**Result:** 264 of 307 reference parts are connected exactly as specified, including all ICs (LM5164-Q1, ESP32
pinout apart from E1, decoders, ADS1220, REF5045, PCA9685), 20 of the 21 measurement PhotoMOS, all BAT54A and all
LEDs. Of the 43 differing parts, 32 are the bleed resistors of one repeated error (E2) and 4 are the intended
address-LED change (S3). 6 errors must be fixed before layout; 3 points need a decision.

## Errors (must fix)

| # | Where | Finding | Fix |
|---|---|---|---|
| E1 | MCU, U201 pin 2 (3V3) | on net `VCC`, which has no other pin → **ESP32 not powered** | net label/power port `+3V3` |
| E2 | BALANCING, R603/R604 … R663/R664 (all 16 channels) | the bleed resistors go from `BAL_Rn` to `T(n−1)_F` – the same tap as the PhotoMOS → the balancing current circulates in a loop, **no cell is balanced** | second terminal of both resistors of channel n to `Tn_F` (cell n is between `T(n−1)_F` and `Tn_F`) |
| E3 | MEAS_MUX, K416 pin 3 | not connected (should be `BUS_B`) → **tap T15 cannot be measured, cells 15 and 16 fail** | connect K416.3 to `BUS_B` |
| E4 | BALANCING, K616 pin 1 and R661 pin 2 | on net `K615_LED` → drive outputs of channels 15 and 16 shorted through R657/R661 | net `K616_LED` |
| E5 | POWER, D103 (PMEG6020ER) | reversed: K on `VBUS`, A on `+5V` → USB cannot supply the board, the board feeds the PC's USB port | K to `+5V`, A to `VBUS` |
| E6 | CELLS, R323 | on nets `ACT_BAL_EN_PWM` / `ACT_BAL_EN_PWM_OUT` (label typo); the MCU side has no other pin → active balancer clock not connected | labels `ACT_BAL_PWM` / `ACT_BAL_PWM_OUT` (J302.4 moves with it) |

## Should fix

| # | Where | Finding | Proposal |
|---|---|---|---|
| S1 | ADC, NT501 missing | `FC_GND` (K420.3, K421.3, R503) is merged into `GND`; the star point of layout rule 3 is no longer visible to the layout/DRC | keep the net `FC_GND` and join it to `GND` at the ADC with a net tie, or a 0 Ω 0603 resistor if EasyEDA has no net-tie part |
| S2 | SCREW1…4 (Screw-Hole-M4) | **plated** holes (Ø 4.0 mm, 4.5 mm copper ring) – SHW-060/061 require reinforced insulation (600 V) to the enclosure | non-plated hole, copper keep-out ≥ 6.5 mm around it; or plated only with insulated (nylon) mounting – decide with the enclosure |
| S3 | MCU, new address LEDs D230…D233 with R215…R218 = 1 kΩ (instead of the 100 kΩ pull-downs) | with a DIP switch open, the input floats (the blue LED does not conduct below ≈ 2.5 V) | keep the LEDs only together with 100 kΩ pull-downs on ADDR0…3 (4 more resistors), or drop them and show the address with the status LED at boot. With LEDs: ≈ 0.3–0.5 mA each from 3.3 V (blue LEDs are dim at 3.3 V; red/green are brighter), also in deep sleep → low-power budget ≈ 0.6 mA instead of 0.36 mA (still ≤ 1 mA, SHW-045) |

## Accepted deviations (to be taken into the reference netlist)

| Item | Drawn | Note |
|---|---|---|
| Designators | C404, D1, F1 | please rename to C402, D101, F101 (traceability to the specification), otherwise the reference follows |
| Connectors J101, J301…J306 | MX15EDGRM-3.5 pluggable series (C5188341/55/43/42) | in stock; the 18-pin J301 has only 77 pcs → order early. DS18B20 and active balancer now on 3.5 mm pluggable instead of JST-XH: fine |
| J201 USB-C | TYPE-C 16PIN 2MD(073), C2765186 | pinout checked (A/B pads, shell on `USB_SHIELD`) |
| SW201, SW202 | 1TS005F-2500-5001 (4 pads) | pads 1/2 and 3/4 connected inside – correct |
| SW203 | 2.54-4P TPGT, C6331176 | |
| D203 | PRTR5V0U2X, C21713980 (other manufacturer) | same pinout |
| R213, R214 | 1 kΩ instead of 820 Ω / 390 Ω | LED current ≈ 1.3 mA, fine |
| C106, C107 | CL31A226KAHNNNE (22 µF 25 V X5R 1206) | fine |

## Next check

After the fixes: "Update PCB from schematic" in EasyEDA, then run the command above again – it reports only the
remaining differences.

## Follow-up (2026-11-24, second draft)

| Item | Status |
|---|---|
| E1…E6 | ✅ fixed |
| Designators C402, D101, F101 | ✅ renamed |
| S3 address LEDs | ✅ pull-downs back (R225, R227, R229, R231 = 100 kΩ); LED resistors R226…R232. Decision: LEDs red/green with **4.7 kΩ** (≈ 0.28 mA each) – with 1 kΩ the low-power budget would rise to ≈ 0.9 mA (spec section 12.1) → **to do** |
| S1 star point | decision: R504 0 Ω 0603 between `FC_GND` (K420.3, K421.3, R503) and `GND`, at the ADC → **to do** |
| S2 mounting holes | decision: plated M4 holes stay; nylon screws/spacers and an insulating enclosure only |
| Accepted deviations | taken into the reference netlist and the specification (0.2, section 2 rows 12…14) |

Remaining differences reported by the check: R504 missing (FC_GND merged into GND), R226/R228/R230/R232 1 kΩ
instead of 4.7 kΩ.
