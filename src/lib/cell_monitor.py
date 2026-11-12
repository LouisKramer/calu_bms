# cell_monitor.py - Cell voltage acquisition for CALU BMS slave (12x ADS1118 behind SN74HC154)
import asyncio
import json
import os
from lib.ADS1118 import ADS1118

TAP_GND = 0
TAP_B_BOT = 99
MUX_SE = (0b100, 0b101, 0b110, 0b111)
_DR_SPS = (8, 16, 32, 64, 128, 250, 475, 860)
_RAW_LIMIT = 32700            # ~full scale -> saturated / no device (MISO pulled up)


class CellMonitor:
    """
    Reads every divided cell tap single-ended against GND (= BA1-) and derives cell voltages.

    Wiring convention for fewer than 16 cells in a string: the balance wires of all
    unused taps of that string are bridged to the string's top tap. String A's top
    must always reach BA16+ because the 5 V buck converter is fed from there.
    """

    def __init__(self, spi, demux, adc_map, cells_a, cells_b, nr_adc_a=6, pga=2, dr=4,
                 cal_file="/data/tap_cal.json", tap_tolerance=0.05, log=None):
        self.cells_a = cells_a
        self.cells_b = cells_b
        self.log = log
        self.cal_file = cal_file
        self.tap_tolerance = tap_tolerance   # V, allowed deviation of duplicate taps
        self._conv_ms = int(1000 / _DR_SPS[dr] * 1.2) + 1
        rows = adc_map[:nr_adc_a] + (adc_map[nr_adc_a:] if cells_b > 0 else ())
        self.rows = rows
        self.adcs = [
            ADS1118(spi, demux=demux, demux_output=y, pga=pga, dr=dr,
                    channel_mux={i: MUX_SE[i] for i in range(4)},
                    gain=[1.0] * 4, cal_file=None)
            for y, _, _ in rows
        ]
        self.gain = {}            # "Y.ch" -> gain correction
        self._load_cal()
        # Physical cell numbers (1..32) of the configured cells, used for balancing
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
        Per-channel gain calibration against reference cell voltages (e.g. from a DMM)
        for the configured cells in order. Requires a fresh scan() just before.
        """
        if self.last is None or len(true_cells) != len(self.cell_ids):
            raise ValueError("scan() first and pass one reference per configured cell")
        true_tap = {TAP_GND: 0.0}
        acc = 0.0
        for n, v in zip(self.cell_ids[:self.cells_a], true_cells[:self.cells_a]):
            acc += v
            true_tap[n] = acc
        for n in range(self.cells_a + 1, 17):
            true_tap[n] = acc
        if self.cells_b:
            # String B bottom equals string A top when stacked
            true_tap[TAP_B_BOT] = acc
            for n, v in zip(self.cell_ids[self.cells_a:], true_cells[self.cells_a:]):
                acc += v
                true_tap[n] = acc
            for n in range(17 + self.cells_b, 33):
                true_tap[n] = acc
        for (y, ch, tap, v_uncal) in self.last["channels"]:
            if tap == TAP_GND or v_uncal is None or v_uncal <= 0:
                continue
            if tap in true_tap:
                self.gain[f"{y}.{ch}"] = true_tap[tap] / v_uncal
        self._save_cal()

    # ------------------------------------------------------------------
    # Acquisition
    # ------------------------------------------------------------------
    async def _read_raw(self):
        """Pipelined single-shot: all ADCs convert the same channel in parallel."""
        raw = [[0] * 4 for _ in self.adcs]
        for ch in range(5):
            for i, adc in enumerate(self.adcs):
                prev = adc.transfer(MUX_SE[ch if ch < 4 else 0])
                if ch > 0:
                    raw[i][ch - 1] = prev
            if ch < 4:
                await asyncio.sleep_ms(self._conv_ms)
        return raw

    async def scan(self):
        raw = await self._read_raw()
        faults = []
        channels = []                     # (Y, ch, tap, uncalibrated tap voltage)
        taps = {}                         # tap -> list of calibrated readings
        for i, (y, tap_ids, ratios) in enumerate(self.rows):
            adc = self.adcs[i]
            for ch in range(4):
                r = raw[i][ch]
                tap = tap_ids[ch]
                if abs(r) >= _RAW_LIMIT:
                    faults.append(f"ADC Y{y} AIN{ch} saturated/absent (raw={r})")
                    channels.append((y, ch, tap, None))
                    continue
                v = adc.raw_to_volt(r) * ratios[ch]
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

        cells = [None] * len(self.cell_ids)
        str_v = [None, None]

        def get(t):
            return tap_v.get(t)

        def diff(a, b):
            va, vb = get(a), get(b)
            return None if va is None or vb is None else va - vb

        # String A
        for k in range(1, self.cells_a + 1):
            cells[k - 1] = diff(k, k - 1)
        top_a = get(self.cells_a)
        str_v[0] = top_a
        self._check_bridged(range(self.cells_a + 1, 17), top_a, tap_v, faults)

        # String B
        link = None
        if self.cells_b:
            for j in range(1, self.cells_b + 1):
                tap = 16 + j
                lower = TAP_B_BOT if j == 1 else tap - 1
                cells[self.cells_a + j - 1] = diff(tap, lower)
            top_b = get(16 + self.cells_b)
            str_v[1] = diff(16 + self.cells_b, TAP_B_BOT)
            self._check_bridged(range(17 + self.cells_b, 33), top_b, tap_v, faults)
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
        """Internal die temperature of every ADS1118 (board temperature map)."""
        res = []
        for adc in self.adcs:
            try:
                res.append(await adc.read_temperature())
            except Exception:
                res.append(None)
        return res
