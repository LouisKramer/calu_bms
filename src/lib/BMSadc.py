import asyncio
from lib.ADS1118_V2 import ADS1118
from lib.SN74HC154 import SN74HC154
from common.common import battery
from common.HAL import slave_hal as HAL
from common.logger import Logger


class BMSadc:
    NUM_ADCS = 12

    MUX_CONFIGS = [
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 0 → cells 0-2
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 1 → cells 3-5
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 2 → cells 6-8
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 3 → cells 9-11
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 4 → cells 12-14
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN2_AIN3],                         # adc 5 → cell 15 + Vstr1 (cells 1-16)
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 6 → cells 16-18
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 7 → cells 19-21
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 8 → cells 22-24
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 9 → cells 25-27
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 10 → cells 28-30
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN2_AIN3],                         # adc 11 → cell 31 + Vstr2 (cells 17-32)
    ]

    # ====================== REAL CALIBRATION GAINS ======================
    CELL_GAINS = [
        1.0, 1.0, 1.017,      # cell  1-3   (ADC 0)
        1.0, 1.01, 1.0,       # cell  4-6   (ADC 1)
        1.0, 1.0, 1.0,        # cell  7-9   (ADC 2)
        1.0, 1.0, 1.0,        # cell 10-12  (ADC 3)
        1.0, 0.964, 1.0,      # cell 13-15  (ADC 4)
        1.0, 1.0,             # cell 16 + Vstr1 (cells 1-16)   ← ADC5
        0.971, 1.0, 1.0,      # cell 17-19  (ADC 6)
        1.025, 0.976, 1.023,  # cell 20-22  (ADC 7)
        0.978, 1.021, 0.98,   # cell 23-25  (ADC 8)
        0.942, 1.019, 0.982,  # cell 26-28  (ADC 9)
        0.948, 1.017, 0.984,  # cell 29-31  (ADC 10)
        0.953, 0.925          # cell 32 + Vstr2 (cells 17-32)  ← ADC11
    ]

    # Auto-build GAIN_CONFIGS (includes gains for string voltages)
    GAIN_CONFIGS = []
    start = 0
    for cfg in MUX_CONFIGS:
        length = len(cfg)
        GAIN_CONFIGS.append(CELL_GAINS[start:start + length])
        start += length

    # Number of *cell* channels per ADC (string voltages are NOT counted as cells)
    CELL_COUNTS = [3, 3, 3, 3, 3, 1, 3, 3, 3, 3, 3, 1]

    def __init__(self, spi):
        self.decoder = SN74HC154(
            enable_pin=HAL.CS_EN_PIN,
            a0_pin=HAL.SPI_CS0_PIN,
            a1_pin=HAL.SPI_CS1_PIN,
            a2_pin=HAL.SPI_CS2_PIN,
            a3_pin=HAL.SPI_CS3_PIN
        )
        self.adcs = [ADS1118(spi=spi) for _ in range(BMSadc.NUM_ADCS)]

        # Correct cell offsets (only normal cells)
        self.cell_offsets = [0]
        for count in BMSadc.CELL_COUNTS[:-1]:
            self.cell_offsets.append(self.cell_offsets[-1] + count)

        self._adc_task = None

        # String voltage storage
        self.v_str1 = 0.0   # sum cells 1-16
        self.v_str2 = 0.0   # sum cells 17-32
        self.v_str  = 0.0   # total pack voltage

        self.log = Logger()

    async def start_all_continuous_scans(self, pga=None, data_rate=None):
        """Call once at startup (must be awaited)"""
        for i in range(BMSadc.NUM_ADCS):
            self.decoder.select(i + 1)
            await self.adcs[i].start_continuous_scan(
                mux_list=BMSadc.MUX_CONFIGS[i],
                gain_list=BMSadc.GAIN_CONFIGS[i],
                pga=pga,
                data_rate=data_rate
            )
            self.decoder.deselect(i + 1)
            await asyncio.sleep_ms(1)

    async def read_one_round(self, bat: battery):
        """Read one sample from every ADC + handle string voltages"""
        for i in range(BMSadc.NUM_ADCS):
            self.decoder.select(i + 1)
            idx, vol = await self.adcs[i].read_scan()

            # === NORMAL CELL VOLTAGE ===
            if not ((i == 5 or i == 11) and idx == 1):   # skip the two string channels
                cell_idx = self.cell_offsets[i] + idx
                value = vol if (vol is not None and vol > 0.5) else -1.0
                bat.meas.set_vcell(cell_idx, value)

            # === STRING VOLTAGE HANDLING ===
            if i == 5 and idx == 1:      # ADC5 second channel → Vstr1
                self.v_str1 = vol if vol is not None else 0.0
            elif i == 11 and idx == 1:   # ADC11 second channel → Vstr2
                self.v_str2 = vol if vol is not None else 0.0

            self.decoder.deselect(i + 1)

        # Update total string voltage once per round and store it
        self.v_str = self.v_str1 + self.v_str2
        bat.meas.set_vstr(self.v_str)

    async def read_cell_voltages(self, bat: battery, rounds: int = 3):
        """Manual full refresh (still usable)"""
        for _ in range(rounds):
            await self.read_one_round(bat)

    # ====================== BACKGROUND ASYNC TASK ======================
    def start_adc_task(self, bat: battery, interval_ms: int = 150):
        if self._adc_task is not None and not self._adc_task.done():
            self._adc_task.cancel()

        async def adc_reader():
            while True:
                try:
                    await self.read_cell_voltages(bat, rounds=3)
                    await asyncio.sleep_ms(interval_ms)
                except Exception as e:
                    self.log.error(f"[BMSadc] ADC task error: {e}")
                    await asyncio.sleep_ms(1000)

        self._adc_task = asyncio.create_task(adc_reader())
        self.log.info(f"ADC background task started (update every {interval_ms} ms)")

    def stop_adc_task(self):
        if self._adc_task is not None:
            self._adc_task.cancel()
            self._adc_task = None
            self.log.info("ADC background task stopped")

    def is_adc_task_running(self) -> bool:
        return self._adc_task is not None and not self._adc_task.done()