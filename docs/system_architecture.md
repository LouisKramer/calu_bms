# CALU BMS – System Architecture

| | |
|---|---|
| Status | Draft 0.1 |
| Based on | [System requirements](requirements.md) 0.8, [Master requirements](master_requirements.md) 0.5, [Slave requirements](slave_requirements.md) 0.5, [Plausibility check](plausibility_check.md) 0.2 |
| Details | [Master architecture](master_architecture.md), [Slave architecture](slave_architecture.md) |

---

## 1. Physical layout

```
 ┌──────────────────────── battery rack ─────────────────────────┐       ┌─────────── HV box ────────────────────────────┐
 │                                                               │       │                                               │
 │  module 10 (16S)  [slave 10]  ── series link ──┐   (optional) │ BAT+  │  F1 fuse 40 A 1000 V DC                        │
 │  module 9  (16S)  [slave 9]                    │              ├──────►│   │                                            │
 │     ⋮                                          │              │       │   ▼                                            │
 │  module 2  (16S)  [slave 2]                    │              │       │  ┌──────── master board ─────────┐  K1 HV+    │  INV+
 │  module 1  (16S)  [slave 1]  ──────────────────┘              │ BAT−  │  │ SiC TOP  ·  SiC BOT  ·  I sense│──main ─────┼──────►
 │                                                               ├──────►│  │ HV DC/DC · ESP32-S3 · CAN      │  K2 HV−    │  INV−
 │  every module: 16 × LFP 350 Ah, cell taps + 4 temperature     │       │  └────────────────────────────────┘──main ─────┼──────►
 │  sensors to its slave, optional active balancer               │       │  K3 precharge + R_pre (PTC)                    │
 │                                                               │       │  heatsink (PE), PE terminal, CAN RJ45 ─────────┼──► inverter BMS port
 └───────────────────────────────────────────────────────────────┘       └───────────────────────────────────────────────┘
                 ▲ ESP-NOW (2.4 GHz)                                                     ▲ Wi-Fi ──► router ──► Home Assistant (MQTT), web UI
```

- **Modules:** 8 today, up to 10 (16S LFP 350 Ah each). One slave per module, mounted on the module, supplied
  by it, no wired connection to anything else (ESP-NOW only).
- **HV box:** one enclosure with the master board (including the SiC switches on a common heatsink and the
  current sensor), pack fuse, contactors, precharge resistor, HV terminals to the inverter, PE terminal and
  the CAN connector. It can sit at any position of the rack (HW-005); it is connected to the pack ends only.
- **Inverter:** GoodWe GW8KN-ET, battery input 180…600 V, 25 A, BMS CAN on RJ45 pins 4/5.

## 2. Power path (single line)

```
 BAT+ ─F1─┬────────────── SiC TOP ──────── K1 (HV+ main) ──┬──────────── INV+
          │                                                │
          ├── K3 (precharge) ── R_pre (PTC) ───────────────┘
          │
          └─F2 (2 A, 1000 V DC)─► master HV DC/DC (PV15-27B12R3) ─► 12 V (LV domain)

 BAT− ──── current sensor ──── SiC BOT ──────── K2 (HV− main) ─────────────── INV−

 U_BAT measured after F1 (BAT+ − BAT−), U_INV measured between INV+ and INV− (master HV− domain).
```

| Element | Part / rating | Where | Requirement |
|---|---|---|---|
| F1 pack fuse | 1000 V DC, 32…40 A, ≥ 20 kA, gBat/aR (14 × 51 or NH00) | HV box | SAF-005, MHW-028 |
| SiC TOP / BOT | 2 × SCT020H120G3AG back-to-back per pole, on the master | master | SAF-002…004, MHW-020 |
| Current sensor | ACS71240LLCBTR-050B3 in the BAT− path | master HV− domain | MEA-004, MHW-032 |
| K1, K2 main contactors | 12 V coil, ≥ 750 V DC, ≥ 40 A, aux contact, bidirectional breaking | HV box | MHW-025, MHW-027 |
| K3 + R_pre precharge | 12 V coil; R_pre PTC/pulse resistor ≥ 200 J, ≈ 100 Ω | HV box | SAF-006, MHW-026 |
| F2 + HV DC/DC | 2 A 1000 V DC fuse; Mornsun PV15-27B12R3 | master | HW-005, MHW-001 |

**Fuse supervision without extra hardware:** U_BAT is measured after F1; the sum of the module voltages
reported by the slaves is the voltage before F1. A large difference means a blown fuse (MHW-028).

**Connect / disconnect** (MSW-004, all contactors switch without current):

| Step | Connect | Disconnect |
|---|---|---|
| 1 | Insulation measurement (`iso_en`) | SiC TOP and BOT off (current interrupted in µs) |
| 2 | K2 close | wait until \|I\| < 0.5 A |
| 3 | SiC BOT on | K1, K2 open (K3 already open) |
| 4 | K3 close → precharge through R_pre (abort per MSW-007) | check aux contacts |
| 5 | U_INV within `precharge_dv` of U_BAT → K1 close | |
| 6 | SiC TOP on, K3 open | |

## 3. Protection layers

| Layer | Detects | Reaction | Speed | Independent of firmware |
|---|---|---|---|---|
| 1 Gate driver DESAT (1ED3860MC12M) | short circuit in discharge direction (V<sub>DS</sub> of the forward MOSFET rises) | soft turn-off of that pole, fault latched in the driver | ≈ 1 µs | yes |
| 2 Current-sensor FAULT | \|I\| > 50 A, both directions | FLT_N of both drivers pulled low → soft turn-off, latched | ≈ 2 µs | yes |
| 3 Master firmware | cell/temperature/current limits, slave timeouts, insulation | SiC off, then contactors open | 0.1…1 s | – |
| 4 Watchdogs | firmware hang (master 1 s, slave 2 s) | reset → all outputs in safe state | ≤ 2 s | yes |
| 5 Fuse F1 | cable short circuit, failed-short SiC | melts | ms | yes |
| 6 Contactors | emergency break if SiC failed short | open | ≈ 10 ms | – |

Slaves protect themselves locally (balancing off below `cell_uv_warn`, over temperature, without master),
but they never switch the pack current – disconnecting is the master's job.

## 4. Communication

```
               Wi-Fi (router channel)                     CAN 500 kbit/s (BYD HVS/HVM protocol)
 Home Assistant ◄── MQTT ──► MASTER ◄────────────────────────────────────────────────► GW8KN-ET
 Browser ◄──── web UI ─────►   ▲
                               │ ESP-NOW (same channel as Wi-Fi), unencrypted, paired MACs, star
                    ┌──────────┼──────────┬───────── … ──┐
                 slave 1    slave 2    slave 3       slave 10
```

| Link | Content | Timing | Requirement |
|---|---|---|---|
| Master → slaves (broadcast) | time sync / measurement trigger, balancing target, config version | every `meas_period` | MEA-008, BAL-005 |
| Master → slave (unicast) | configuration, balancing commands, OTA, low-power command | on demand | CFG-001, SYS-006 |
| Slave → master | cell voltages, temperatures, module voltage, balancing state, faults | every `meas_period`; events ≤ 200 ms | MEA-002, SWS-023 |
| Master ↔ inverter (CAN) | limits (0x110 every 2 s), SOC/SOH, V/I/T, identification | per protocol | COM-001 |
| Master → Home Assistant | all values, states, faults; writable configuration entities | `mqtt_period` | COM-004, CFG-008 |

Radio channel: `espnow_channel` = `auto` (master follows the router, slaves scan) or 1…13 (router channel fixed).

## 5. Power supply and isolation

| Board / domain | Supplied from | Potential | Isolation to the outside |
|---|---|---|---|
| Slave n | its module (10…60 V) | module n (0…584 V to BAT−) | reinforced ≥ 600 V to enclosure/earth; USB only through a ≥ 1 kV isolator |
| Master LV (ESP32, 12 V coils) | whole pack via PV15-27B12R3 | floating, near PE | reinforced from all HV domains (accessible: USB, contactor coils, LEDs) |
| Master HV− (ADC, current sensor, IMD) | LV via isolated power | BAT− | reinforced to LV/CAN/PE |
| Master HV+ / HV− gate drivers | LV 12 V via QA123C-1803R3 | TOP / BOT source nodes | reinforced to LV; basic between HV+ and HV− |
| Master CAN | ISOW1044 integrated power | inverter CAN ground | reinforced to LV and HV |

Rack, HV box enclosure and the SiC heatsink are connected to PE.

## 6. Function allocation

| Function | Slave | Master | External |
|---|---|---|---|
| Cell voltage, cell temperature, module voltage | ✔ | | |
| Passive balancing (execution), active balancer enable/clock | ✔ | | active balancer |
| Balancing target and coordination | | ✔ | |
| Pack current, U_BAT, U_INV, insulation resistance | | ✔ | |
| Protection decisions, disconnect, precharge | | ✔ | contactors, fuse |
| SOC, SOH, current/voltage limits | | ✔ | |
| Inverter protocol | | ✔ | inverter |
| Configuration master copy, logging (≤ 7 days), HA, web UI, OTA | | ✔ | router, HA |

## 7. Firmware structure (both boards)

```
repo
├─ firmware/
│  ├─ common/        protocol (messages, encoding, sequence/auth), config schema (single source of all
│  │                 parameters: default, range, unit, S-flag), crc, time sync, logging helpers
│  ├─ slave/         hal/ · measurement/ · balancing/ · link/ · app (state machine, low power, console)
│  ├─ master/        hal/ · core/ (states, protection, SOC, limits, balancing) · comm/ (espnow, can, mqtt,
│  │                 web) · app (config store, logger, OTA)
│  └─ build/         custom MicroPython build (ESP32 CAN module, frozen modules) for master and slave
├─ hw/slave/, hw/master/   KiCad (SKiDL) projects
├─ tools/            CAN sniffer/replay, calibration, production test, work-item scripts
└─ tests/            host tests (CPython + pytest) with simulated HAL, slaves and inverter
```

The configuration schema in `common/` is the single source of the parameter table of the system
requirements chapter 9; master, slaves, web UI and HA discovery are generated from it.
