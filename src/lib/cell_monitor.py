# cell_monitor.py - Cell voltage acquisition for CALU BMS slave (12x ADS1118 behind SN74HC154)
import asyncio
import json
import os
from lib.ADS1118 import ADS1118, MUX_SE

TAP_GND = 0          # BA1- = board GND
TAP_B_BOT = 99       # BA17- = bottom of string B
_RAW_LIMIT = 32700   # near full scale -> saturated


class CellMonitor:
    """
    Reads every divided cell tap single-ended against GND (= BA1-) and derives cell voltages.

    String A holds cells 1..cells_a, string B cells 17..16+cells_b (stacked on top of A).
    Fewer than 16 cells per string: bridge the balance wires of all unused taps of that
    string to the string's top tap. String A must always reach BA16+ (buck converter supply).

    Balancing current flows through the tap wires: pause balancing (and let it settle)
    before calling scan().
    """

    def __init__(self, spi, demux, adc_map, cells_a, cells_b, nr_adc_a=6, pga=2, dr=4,
                 min_cells_a=1, cal_file="/data/tap_cal.json", tap_tolerance=0.05):
        if not min_cells_a <= cells_a <= 16:
            raise ValueError(f"cells_a must be {min_cells_a}..16")
        if not 0 <= cells_b <= 16:
            raise ValueError("cells_b must be 0..16")
        self.cells_a = cells_a
        self.cells_b = cells_b
        self.cal_file = cal_file
        self.tap_tolerance = tap_tolerance   # V, allowed deviation of duplicate taps
        self.rows = adc_map[:nr_adc_a] + (adc_map[nr_adc_a:] if cells_b else ())
        self.adcs = [ADS1118(spi, demux=demux, demux_output=y, pga=pga, dr=dr) for y, _, _ in self.rows]
        self._conv_ms = self.adcs[0].conversion_ms
        self._lock = asyncio.Lock()
        self.gain = {}            # "Y.ch" -> gain correction of that input
        self._load_cal()
        # Physical cell numbers (1..32) of the configured cells, also used for balancing
        self.cell_ids = list(range(1, cells_a + 1)) + list(range(17, 17 + cells_b))
        self.last = None

    # ------------------------------------------------------------------
    # Calibration
    # ------------------------------------------------------------------
    def _load_cal(self):
        try:
            with open(self.cal_file) as f:
                self.gain = json.load(f).get("gain", {})
        except (OSError, ValueError):
            self.gain = {}

    def _save_cal(self):
        if "/" in self.cal_file.lstrip("/"):
            try:
                os.mkdir(self.cal_file.rsplit("/", 1)[0])
            except OSError:
                pass
        with open(self.cal_file, "w") as f:
            json.dump({"gain": self.gain}, f)

    def clear_calibration(self):
        self.gain = {}
        self._save_cal()

    def calibrate_from_cells(self, true_cells):
        """
        Per-input gain calibration against reference cell voltages (e.g. DMM), one per
        configured cell in cell_ids order. Requires a fresh scan() with balancing paused.
        """
        if self.last is None or len(true_cells) != len(self.cell_ids):
            raise ValueError("scan() first and pass one reference per configured cell")
        true_tap = {}
        acc = 0.0
        for n, v in zip(self.cell_ids[:self.cells_a], true_cells[:self.cells_a]):
            acc += v
            true_tap[n] = acc
        for n in range(self.cells_a + 1, 17):
            true_tap[n] = acc
        if self.cells_b:
            true_tap[TAP_B_BOT] = acc
            for n, v in zip(self.cell_ids[self.cells_a:], true_cells[self.cells_a:]):
                acc += v
                true_tap[n] = acc
            for n in range(17 + self.cells_b, 33):
                true_tap[n] = acc
        for (y, ch, tap, v_uncal) in self.last["channels"]:
            if tap in true_tap and v_uncal and v_uncal > 0:
                self.gain[f"{y}.{ch}"] = true_tap[tap] / v_uncal
        self._save_cal()

    # ------------------------------------------------------------------
    # Acquisition
    # ------------------------------------------------------------------
    def probe(self):
        """Demux outputs of ADCs that do not echo their config register."""
        return [y for (y, _, _), adc in zip(self.rows, self.adcs) if not adc.probe()[0]]

    async def _read_raw(self):
        """Pipelined single-shot: all ADCs convert the same input in parallel."""
        raw = [[0] * 4 for _ in self.adcs]
        for ch in range(5):
            for i, adc in enumerate(self.adcs):
                prev = adc.transfer(MUX_SE[ch % 4], start=ch < 4)
                if ch:
                    raw[i][ch - 1] = prev
            if ch < 4:
                await asyncio.sleep_ms(self._conv_ms)
        return raw

    async def scan(self):
        async with self._lock:
            missing = self.probe()
            raw = await self._read_raw()
        faults = [f"ADC Y{y} not responding" for y in missing]
        channels = []                     # (Y, ch, tap, uncalibrated tap voltage)
        taps = {}                         # tap -> list of calibrated readings
        for i, (y, tap_ids, ratios) in enumerate(self.rows):
            for ch in range(4):
                r = raw[i][ch]
                tap = tap_ids[ch]
                if y in missing or abs(r) >= _RAW_LIMIT:
                    if y not in missing:
                        faults.append(f"ADC Y{y} AIN{ch} saturated (raw={r})")
                    channels.append((y, ch, tap, None))
                    continue
                v = r * self.adcs[i].lsb * ratios[ch]
                channels.append((y, ch, tap, v))
                taps.setdefault(tap, []).append(v * self.gain.get(f"{y}.{ch}", 1.0))

        tap_v = {}
        mismatch = 0.0
        for tap, vals in taps.items():
            tap_v[tap] = sum(vals) / len(vals)
            if len(vals) > 1:
                d = max(vals) - min(vals)
                mismatch = max(mismatch, d)
                if d > self.tap_tolerance:
                    faults.append(f"Tap {tap} duplicate mismatch {d:.3f} V")

        if abs(tap_v.get(TAP_GND, 0.0)) > self.tap_tolerance:
            faults.append(f"GND reference reads {tap_v[TAP_GND]:.3f} V")
        tap_v[TAP_GND] = 0.0

        def diff(a, b):
            va, vb = tap_v.get(a), tap_v.get(b)
            return None if va is None or vb is None else va - vb

        cells = [diff(k, k - 1) for k in range(1, self.cells_a + 1)]
        str_v = [tap_v.get(self.cells_a), None]
        self._check_bridged(range(self.cells_a + 1, 17), tap_v.get(self.cells_a), tap_v, faults)

        link = None
        if self.cells_b:
            for j in range(1, self.cells_b + 1):
                cells.append(diff(16 + j, TAP_B_BOT if j == 1 else 15 + j))
            top_b = 16 + self.cells_b
            str_v[1] = diff(top_b, TAP_B_BOT)
            self._check_bridged(range(top_b + 1, 33), tap_v.get(top_b), tap_v, faults)
            link = diff(TAP_B_BOT, 16)
            if link is not None and abs(link) > self.tap_tolerance:
                faults.append(f"String link BA17- vs BA16+ differs by {link:.3f} V")

        self.last = {
            "cells": cells,
            "str": str_v,
            "link": link,
            "mismatch": mismatch,
            "taps": tap_v,
            "channels": channels,
            "faults": faults,
        }
        return self.last

    def _check_bridged(self, unused, top, tap_v, faults):
        if top is None:
            return
        for t in unused:
            v = tap_v.get(t)
            if v is not None and abs(v - top) > self.tap_tolerance * 4:
                faults.append(f"Unused tap {t} not bridged to top ({v:.2f} V vs {top:.2f} V)")

    async def read_adc_temperatures(self):
        """Die temperature of every ADS1118 (rough board temperature map)."""
        res = []
        async with self._lock:
            for adc in self.adcs:
                try:
                    res.append(await adc.read_temperature())
                except OSError:
                    res.append(None)
        return res
