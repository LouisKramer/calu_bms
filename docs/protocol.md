# CALU BMS – Master–Slave Protocol (ESP-NOW)

| | |
|---|---|
| Status | 0.2 – design approved 2026-11-23 (decisions in section 10); implementation W-04, issue #5 |
| Requirements | COM-002, COM-003, MEA-002, MEA-008, SAF-010, SAF-011, SAF-017, CFG-001, BAL-005, SWS-002…005, SWS-010…034, SWS-040…050, MSW-008, MSW-010…013 |
| Implementation | `firmware/common/` (codec, sequence filter, time base) – shared by master and slave, testable on the PC |

---

## 1. Requirements covered

| Requirement | How the protocol meets it | Section |
|---|---|---|
| COM-002, SWS-020 ESP-NOW, no encryption, MAC filter | ESP-NOW unicast/broadcast; peers registered at pairing; unknown MACs dropped | 2, 6.1 |
| COM-003, SWS-021 module address, type, sequence, version; discard corrupted/duplicated/out-of-order/foreign | common header with version, type, network ID, address, boot session, sequence; CRC-32 | 3 |
| SWS-025 versioning | major/minor rules; header layout frozen for all versions | 3.3 |
| MEA-002, SWS-022 data every measurement cycle | DATA after every scan | 5.5 |
| MEA-008, SWS-010, SWS-024 measurement synchronised within 100 ms, offset reported | network time in SYNC; measurement on a common time grid; offset in DATA | 6.3 |
| SWS-023 events within 200 ms | EVENT sent immediately after the scan that detected it | 5.6 |
| SAF-010, SAF-011, SWS-031 timeouts | master: last DATA per slave; slave: last SYNC (balancing refresh) | 6.3 |
| CFG-001, SWS-040 configuration with version + checksum, confirmation | CONFIG + CONFIG_ACK; SYNC announces the current version/CRC | 5.2, 6.2 |
| BAL-005, SWS-030, SWS-034 balancing coordination and state | target and per-module cell masks in SYNC; state in DATA | 5.1, 5.5 |
| SAF-017, SWS-005, MSW-008 low-power state | LOW_POWER flag in SYNC, wake-up windows on the time grid | 6.5 |
| SWS-002 self test reported | HELLO | 5.4 |
| SWS-050 fault log on request | COMMAND GET_LOG → RESPONSE | 5.3, 5.7 |
| SYS-006, SWS-043 OTA | message types reserved; transport decided in W-11/W-19 | 4 |

---

## 2. Link layer (ESP-NOW)

| Item | Value / rule |
|---|---|
| Topology | star: one master, up to 10 slaves (`modules_count`) |
| Payload | ≤ 250 bytes per message (ESP-NOW v1; v2 devices accept v1 frames); no fragmentation needed in v1 |
| Master → all slaves | **broadcast** (`ff:ff:ff:ff:ff:ff`): SYNC. No link-layer ACK; lost SYNCs are covered by the time base and the next SYNC |
| Unicast (both directions) | link-layer ACK + hardware retries; `send()` returns whether the peer acknowledged |
| Peers | master registers the paired slave MACs (≤ 10 of 20 peers) + broadcast; slave registers the master MAC + broadcast |
| Encryption | none (decision P4); receiving does not require registration, so every receiver checks the sender MAC itself |
| Channel | `espnow_channel` = `auto`: master uses the channel of its Wi-Fi access point; 1…13: fixed channel (section 6.4) |
| Master Wi-Fi | station power saving **off** (`PM_NONE`), automatic reconnect scanning off, otherwise ESP-NOW frames are lost |
| Rate | 1 Mbit/s (default, longest range) |

---

## 3. Message format

### 3.1 Frame

All multi-byte values little-endian. Total length = 8 + payload + 4 ≤ 250 → payload ≤ 238 bytes.

| Offset | Size | Field | Meaning |
|---|---|---|---|
| 0 | 1 | `ver` | protocol version: major (high nibble), minor (low nibble); v1.0 = `0x10` |
| 1 | 1 | `type` | message type (section 4) |
| 2 | 2 | `net_id` | network ID of this BMS, random, chosen by the master at commissioning; separates neighbouring installations |
| 4 | 1 | `addr` | slave → master: sender's module address; master → slave: target address; `0xFF` = all slaves |
| 5 | 1 | `session` | sender's boot counter (stored non-volatile, +1 per boot) |
| 6 | 2 | `seq` | sender's message counter, +1 per sent message (all types), wraps at 65535 |
| 8 | n | payload | type specific (section 5) |
| 8 + n | 4 | `crc` | CRC-32 (IEEE, as `binascii.crc32`) over bytes 0 … 7 + n |

Module addresses: 1…10 from the DIP switch (`0` = switch not set → the slave refuses RUN); master = `0`.

### 3.2 Receive checks (in this order; a failed check drops the frame and counts it)

1. Sender MAC is a paired peer (exception: HELLO during an open pairing window).
2. Length 12…250 bytes; CRC correct.
3. `ver` major equals ours (else: slave reports VERSION_MISMATCH in HELLO and stays out of RUN).
4. `net_id` equals ours (exception: pairing).
5. `addr` is ours or `0xFF` (slave); for the master: `addr` matches the address paired with this MAC.
6. Sequence filter (3.4) accepts `session`/`seq`.
7. Payload length ≥ the minimum for this type and version; unknown `type` → ignored (counted).

### 3.3 Versioning (SWS-025)

- The header (3.1) never changes.
- **Minor** version: only additions – new message types, new fields appended at the end of a payload, new
  configuration parameter IDs. Receivers ignore unknown types, trailing payload bytes and unknown parameter IDs.
- **Major** version: anything incompatible. Master and slaves must have the same major version to operate;
  HELLO carries both versions so the master can show the mismatch.

### 3.4 Sequence filter (duplicates, out of order)

Per sender (MAC): store last `session` and `seq`.

- `session` differs from the stored one → sender rebooted → accept, store.
- Else accept only if `0 < (seq − last_seq) mod 65536 < 32768` (newer), store; otherwise drop (duplicate or old).
- Gaps are allowed (a slave does not see the master's unicasts to other slaves).

### 3.5 Units

| Quantity | Encoding |
|---|---|
| Cell voltage, voltage limits | `u16`, 0.1 mV (0 … 6.5535 V) |
| Module voltage | `u16`, 2 mV (0 … 131 V) |
| Temperature | `i16`, 0.1 °C; `-32768` = not available |
| Time | `u32` network time in ms (wraps after 49.7 days; all comparisons modulo 2³²) |
| Durations in configuration | `u32` ms |

---

## 4. Message types

| Type | Name | Direction | Transport | When |
|---|---|---|---|---|
| `0x01` | SYNC | master → all | broadcast | every `meas_period`; 10 × per second while pairing is open |
| `0x02` | CONFIG | master → slave | unicast | after HELLO with a different config version/CRC, after a configuration change |
| `0x03` | COMMAND | master → slave | unicast | on demand |
| `0x81` | HELLO | slave → master | unicast (broadcast while pairing) | at boot, when the master is found again, on request |
| `0x82` | DATA | slave → master | unicast | after every scan |
| `0x83` | EVENT | slave → master | unicast | immediately on a limit violation or fault |
| `0x84` | CONFIG_ACK | slave → master | unicast | after CONFIG |
| `0x85` | RESPONSE | slave → master | unicast | answer to COMMAND |
| `0x40…0x4F` | reserved: OTA | both | unicast | slave firmware update (W-11/W-19) |

---

## 5. Payloads (v1.0)

### 5.1 SYNC (master → all, broadcast)

| Size | Field | Meaning |
|---|---|---|
| 4 | `net_time` | master network time (ms) when the frame is handed to the radio |
| 2 | `meas_period` | ms (500 … 1000); measurements start at every multiple of `meas_period` of the network time |
| 1 | `master_state` | INIT, STANDBY, PRECHARGE, CONNECTED, DERATED, FAULT, SERVICE, SNIFF, LOW_POWER |
| 1 | `flags` | bit 0 PAIRING_OPEN, bit 1 LOW_POWER (slaves enter the low-power state), bit 2 MEASURE_NOW (extra scan, service) |
| 2 | `cfg_version` | current configuration version |
| 4 | `cfg_crc` | CRC-32 of the current slave configuration (5.2) |
| 1 | `bal_mode` | 0 = off, 1 = master selects cells (masks below), 2 = slave selects cells above the target (`bal_start_v`, `bal_delta`) |
| 2 | `bal_target` | balancing target voltage, 0.1 mV |
| 2 | `lp_period` | low-power wake-up period, s (default 600) |
| 1 | `n` | number of masks that follow (= `modules_count`) |
| 2 × n | `bal_mask[i]` | cells to balance in module i + 1 (bit 0 = cell 1); valid for `bal_mode` 1 |

Size: 20 + 2 × 10 = 40 bytes. Every valid SYNC also refreshes the slave's balancing timeout (`slave_bal_timeout`).

### 5.2 CONFIG (master → slave)

| Size | Field | Meaning |
|---|---|---|
| 2 | `cfg_version` | |
| 4 | `cfg_crc` | CRC-32 over the parameter list (sorted by ID, encoded as below) |
| 1 | `count` | number of parameters |
| 5 × count | `id` (u8) + `value` (i32) | slave parameters, scaled integers (table below) |

v1.0 slave parameters (the configuration schema of W-03 takes over these IDs):

| ID | Parameter | Scale | ID | Parameter | Scale |
|---|---|---|---|---|---|
| 1 | `cells_per_module` | 1 | 13 | `t_discharge_max` | 0.1 °C |
| 2 | `temp_sensor_count` | 1 | 14 | `t_trip_margin` | 0.1 K |
| 3 | `meas_period` | ms | 15 | `t_board_max` | 0.1 °C |
| 4 | `plaus_tol` | 0.01 % | 16 | `slave_timeout_trip` | ms |
| 5 | `cell_ov_trip` | 0.1 mV | 17 | `slave_bal_timeout` | ms |
| 6 | `cell_ov_warn` | 0.1 mV | 18 | `bal_passive_en` | 0/1 |
| 7 | `cell_uv_warn` | 0.1 mV | 19 | `bal_active_en` | 0/1 |
| 8 | `cell_uv_trip` | 0.1 mV | 20 | `bal_start_v` | 0.1 mV |
| 9 | `cell_v_hyst` | 0.1 mV | 21 | `bal_delta` | 0.1 mV |
| 10 | `t_charge_min` | 0.1 °C | 22 | `bal_active_freq` | Hz |
| 11 | `t_charge_max` | 0.1 °C | 23 | `espnow_channel` | 0 = auto, 1…13 |
| 12 | `t_discharge_min` | 0.1 °C | | | |

Size: 7 + 5 × 23 = 122 bytes. The slave validates ranges and cross-checks with the same schema as the master (W-03).

### 5.3 COMMAND (master → slave)

| Size | Field | Meaning |
|---|---|---|
| 1 | `cmd` | 1 IDENTIFY (blink LEDs 10 s), 2 REBOOT, 3 SELF_TEST, 4 GET_LOG, 5 CLEAR_LOG, 6 PAIR_ACCEPT, 7 UNPAIR, 8 GET_HELLO |
| 1 | `token` | chosen by the master, echoed in RESPONSE |
| n | `args` | GET_LOG: start index (u8), count (u8); PAIR_ACCEPT: `net_id` (u16), channel (u8) |

### 5.4 HELLO (slave → master)

| Size | Field | Meaning |
|---|---|---|
| 1 | `proto_major_minor` | same as `ver` (kept in the payload for the mismatch report) |
| 3 | `fw_version` | major, minor, patch |
| 1 | `hw_version` | board revision (40 = 4.0) |
| 1 | `state` | INIT 0, SEARCH 1, CONFIG 2, RUN 3, FAULT 4, LOW_POWER 5 |
| 1 | `reset_reason` | power-on, watchdog, brown-out, software, deep-sleep wake |
| 2 | `self_test` | bit field: ADC, reference, balancing driver, DS18B20 count, supply, calibration valid, address valid, … |
| 2 | `cfg_version` | stored configuration |
| 4 | `cfg_crc` | |
| 4 | `uptime` | s |
| 1 | `flags` | bit 0 VERSION_MISMATCH, bit 1 PAIRED, bit 2 ADDRESS_CONFLICT_SUSPECTED |

Size: 20 bytes.

### 5.5 DATA (slave → master)

| Size | Field | Meaning |
|---|---|---|
| 4 | `t_meas` | network time of the scan start (= grid point; cycle = `t_meas / meas_period`) |
| 1 | `state` | slave state |
| 4 | `faults` | bit field (5.8), current state |
| 2 | `time_offset` | i16 ms: last measured deviation of the slave's network-time estimate from SYNC (SWS-024) |
| 2 | `v_module` | module voltage (2 mV) |
| 2 | `bal_mask` | cells currently balancing |
| 1 | `bal_duty` | % of the last cycle the balancing was active (scan pause excluded) |
| 1 | `n_t` | number of temperatures that follow |
| 2 × n_t | `temp[]` | external 1…4, NTC at the bleed resistors, ADC die (0.1 °C) |
| 1 | `n_c` | number of cells (`cells_per_module`) |
| 2 × n_c | `cell[]` | calibrated cell voltages (0.1 mV) |

Size with 16 cells and 6 temperatures: 18 + 12 + 32 = 62 bytes (+ 12 header/CRC = 74).

### 5.6 EVENT (slave → master)

| Size | Field | Meaning |
|---|---|---|
| 4 | `t` | network time of detection |
| 1 | `count` | events in this message (≤ 16) |
| 12 × count | `code` (u8), `index` (u8, cell or sensor), `active` (u8: 1 set, 0 cleared), reserved (u8), `value` (i32), `limit` (i32) – value and limit in the unit of the quantity (cell voltage 0.1 mV, temperature 0.1 °C) | codes: CELL_OV_WARN, CELL_OV_TRIP, CELL_UV_WARN, CELL_UV_TRIP, T_CHARGE_LOW/HIGH, T_DISCHARGE_LOW/HIGH, T_BOARD_HIGH, plus every fault bit of 5.8 (`0x40` + bit number) |

### 5.7 CONFIG_ACK and RESPONSE (slave → master)

CONFIG_ACK: `cfg_version` (u16), `cfg_crc` (u32), `result` (u8: 0 OK, 1 CRC error, 2 out of range, 3 cross-check failed, 4 unknown required ID, 5 storage error), `param_id` (u8, first failing parameter).

RESPONSE: `cmd` (u8), `token` (u8), `result` (u8), `data` (≤ 235 bytes; GET_LOG: index (u8), total (u8), then
up to 14 log entries of 16 bytes: time u32, code u8, index u8, reserved u16, value i32, value2 i32).

### 5.8 Fault bits (`faults`, SWS-013)

| Bit | Fault | Bit | Fault |
|---|---|---|---|
| 0 | open tap wire | 8 | ADC not responding |
| 1 | cell voltage out of measurement range | 9 | reference / supply out of range |
| 2 | module voltage vs. cell sum outside `plaus_tol` | 10 | calibration data invalid |
| 3 | unused tap not at top-tap voltage (SWS-014) | 11 | configuration invalid / missing |
| 4 | temperature sensor missing | 12 | address invalid or conflict |
| 5 | temperature sensor faulty | 13 | protocol version mismatch |
| 6 | board over-temperature | 14 | balancing stopped by local protection |
| 7 | stuck tap switch (diagnostic scan) | 15 | last reset by watchdog |

---

## 6. Procedures

### 6.1 Pairing (commissioning)

```
user (web UI): "pair slaves"      → master: SYNC with PAIRING_OPEN, 10 × per second, for 5 min
unpaired slave (SEARCH)           → scans channels, receives SYNC(PAIRING_OPEN), registers master MAC
                                  → HELLO (broadcast, addr from DIP, flags.PAIRED = 0)
master                            → lists slave (address, MAC, firmware) in the web UI
user: accept                      → master stores MAC ↔ address, COMMAND PAIR_ACCEPT(net_id, channel)
slave                             → stores master MAC + net_id (non-volatile), RESPONSE OK → paired
```

- A slave only reacts to PAIRING_OPEN while it is unpaired (new board, or after UNPAIR / service console).
- Two slaves with the same address: the master rejects the second and shows the conflict.

### 6.2 Start-up, discovery and configuration

```
slave boot → INIT (safe outputs, self test) → SEARCH: find master (6.4), wait for SYNC
SYNC received → time base set → HELLO(cfg_version, cfg_crc, self_test)
   ├─ cfg equal to SYNC  → RUN
   └─ cfg different      → CONFIG state; master sends CONFIG → slave validates, stores → CONFIG_ACK(OK) → RUN
                           (rejected → stays in CONFIG, master shows the error)
master: operation (connect) only when all `modules_count` slaves are in RUN with the current cfg (MSW-010)
```

A configuration change on the master → new `cfg_version`/`cfg_crc` in SYNC → every slave answers with HELLO
(different cfg) → CONFIG → CONFIG_ACK. Slaves keep running with the old configuration until the new one is
confirmed; the master does not connect while any slave has a different version (CFG-001).

### 6.3 Cyclic operation and time synchronisation

```
network time ─|──────────────── meas_period ────────────────|───────
master        SYNC(net_time)                                SYNC
slave k       scan (≈ 0.34 s) ── wait addr × 10 ms ── DATA  scan …
              └─ EVENT immediately if a limit is crossed
```

- **Time base:** at each SYNC the slave computes `offset = net_time − local_ms + latency` (latency constant
  ≈ 1 ms, measured once on hardware) and filters it (median of the last 5). `time_offset` in DATA reports the
  deviation of the estimate at the latest SYNC.
- **Measurement grid:** every slave starts a scan when its network time crosses a multiple of `meas_period`.
  This keeps all slaves within a few ms of each other (MEA-008: 100 ms), also when single SYNCs are lost
  (crystal drift ≈ 20 ppm → 20 µs/s).
- **Send slot:** DATA is sent `addr × 10 ms` after the scan ends, to avoid collisions of 10 slaves.
- **Timeouts:** master: no DATA from a slave for `slave_timeout_fault` / `slave_timeout_trip` (SAF-010).
  Slave: no valid SYNC for `slave_bal_timeout` → balancing off (SWS-031); for `slave_timeout_trip` → SEARCH
  (and low-power state if a cell is below `cell_uv_warn`, SWS-005).

### 6.4 Channel search

- Paired slave, `espnow_channel` = auto: send HELLO unicast to the stored master MAC on channel 1, 2, … 13;
  the link-layer ACK shows the master's channel (≈ 13 × 10 ms). Retry every 5 s while not found.
- Fixed channel: use it directly.
- Unpaired slave: listen 150 ms per channel for SYNC with PAIRING_OPEN (sent at 10 Hz while pairing).

### 6.5 Low-power state (SAF-017)

- Master sets LOW_POWER in SYNC for 10 s; slaves stop balancing, answer with DATA (state LOW_POWER) and sleep.
- Wake-up on the network-time grid of `lp_period` (600 s): slave wakes early, listens for SYNC up to a listen
  window, scans, sends DATA, sleeps; master wakes for a slightly longer window and broadcasts SYNC every 100 ms.
- **Open risk (W-11):** the ESP32 RC clock in deep sleep drifts by up to a few % → the listen window must cover
  the drift (± 6 s at 1 % over 600 s); each wake-up re-synchronises. The window length is measured on hardware.

---

## 7. Timing and air time

| Traffic | Size | Rate | Air time at 1 Mbit/s |
|---|---|---|---|
| SYNC | 52 B | 1/s | ≈ 0.6 ms |
| DATA × 10 | 74 B | 10/s | ≈ 10 × 0.8 ms |
| EVENT, CONFIG, HELLO | ≤ 134 B | rare | – |
| **Total** | | | **≈ 1 % of the channel** |

Latency budget for SWS-023: scan end → EVENT sent < 20 ms (no send slot for events); limit violation → master
reaction is dominated by the master's 100 ms protection cycle.

---

## 8. Library design (`firmware/common/`)

| Module | Content |
|---|---|
| `crc.py` | `crc32(data)` – `binascii.crc32` (C implementation on MicroPython), pure-Python fallback |
| `protocol.py` | constants (version, types, states, flags, fault bits, event codes, parameter IDs and scales), message records (`collections.namedtuple`, available in MicroPython), `encode(header, msg) → bytes`, `decode(frame) → (header, msg)` with the checks of 3.2 (length, CRC, version, payload); `ProtocolError(code)` |
| `seqfilter.py` | `SeqCounter` (session + seq for sending), `SeqFilter.accept(mac, session, seq)` (3.4) |
| `timebase.py` | network-time estimate from SYNC (offset filter), modulo-2³² arithmetic, grid helpers (`next_grid`, `cycle_of`) |

Rules: pure Python, no `machine`/`espnow` imports (radio access stays in `slave/link/` and `master/comm/`,
W-11 / W-17); `struct.pack_into` / `unpack_from` on preallocated buffers; no allocations in the decode path
beyond the result record; MicroPython subset only.

---

## 9. Test plan

### 9.1 Host tests (pytest, CPython) – `tests/common/`

| ID | Test | Pass criterion |
|---|---|---|
| T01 | Round trip of every message type with typical, minimum and maximum values (4 and 16 cells, 0 and 6 temperatures, 0 and 10 masks) | decoded == original |
| T02 | Scaling: cell voltages 0…6.5535 V | round-trip error ≤ 0.05 mV; out-of-range values raise on encode |
| T03 | Maximum sizes: DATA (16 cells, 6 temps), CONFIG (all parameters), SYNC (10 masks), RESPONSE (max log) | ≤ 250 bytes |
| T04 | Every single-bit flip of a valid frame | rejected (CRC) |
| T05 | Truncated frames (every length < valid) and frames > 250 bytes | rejected with the right code |
| T06 | Wrong `net_id`, wrong `addr`, major version + 1 | rejected with the right code |
| T07 | Minor version + 1 with extra trailing payload bytes, unknown type, unknown parameter ID | accepted / ignored as specified (3.3) |
| T08 | Sequence filter: in order, duplicate, older, gap, wrap 65535 → 0, session change | accept/drop per 3.4 |
| T09 | Time base: simulated SYNCs with latency jitter (± 2 ms) and 20 % loss; ms wrap at 2³² | estimate within ± 5 ms; grid start identical for 10 simulated slaves |
| T10 | Configuration CRC: same parameter set in different order → same CRC; one value changed → different CRC | |
| T11 | Golden vectors: one encoded frame per type stored in `tests/common/vectors_v1.json` (regenerate only after an intended format change with a version bump: `UPDATE_VECTORS=1 pytest -k golden`) | encoder output matches byte for byte (protects the wire format against accidental changes) |
| T12 | MicroPython syntax: `mpy-cross` compiles all `firmware/common/*.py` (skipped if not installed) | no errors |

### 9.2 On-device tests (MicroPython, `tools/espnow_bench/`)

| ID | Setup | Test | Pass criterion |
|---|---|---|---|
| H01 | 1 board | decode/encode the golden vectors of T11 on MicroPython | identical bytes |
| H02 | 2 boards (master/slave role) | pairing, HELLO, CONFIG/CONFIG_ACK, 10 min cyclic SYNC + DATA at 1 s | 0 lost DATA after retries; decode errors 0 |
| H03 | 2 boards | channel search: master changes channel | slave finds it within 2 s |
| H04 | 2 boards + logic analyser | both toggle a GPIO at each grid point | skew < 10 ms (requirement 100 ms) |
| H05 | 2 boards | encode/decode time per message, RAM use | decode < 2 ms; no growth of the heap over 10 min |

Done criterion of W-04: T01…T12 pass. H01…H05 need two ESP32-S3 boards (none available yet, D5); they move to
W-11/W-17 together with the radio transport code.

---

## 10. Decisions (2026-11-23)

| # | Question | Decision |
|---|---|---|
| D1 | Balancing commands in the broadcast SYNC (masks for all modules) or as unicast per slave | **SYNC broadcast**: one frame per cycle, refreshes all slaves at once; a lost SYNC only delays by one cycle |
| D2 | Configuration encoding | **ID/value list** (extensible with minor versions), not a fixed structure |
| D3 | Frame CRC | **CRC-32** (C implementation in MicroPython, 4 bytes) in addition to the link-layer FCS: also catches software errors and foreign ESP-NOW traffic |
| D4 | Slave OTA transport (later work item) | **ESP-NOW chunks** (no Wi-Fi credentials on the slaves, works on a fixed channel); type range reserved |
| D5 | Hardware for H01…H05 | **none yet** → on-device tests later (W-11/W-17) |
