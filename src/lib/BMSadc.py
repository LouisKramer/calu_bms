import asyncio
from lib.ADS1118_V2 import ADS1118
from lib.SN74HC154 import SN74HC154
from common.common import battery
from common.HAL import slave_hal as HAL
from common.logger import Logger


class BMSadc:
    NUM_ADCS = 12

    MUX_CONFIGS = [
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 0
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 1
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 2
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 3
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 4
        [ADS1118.MUX_AIN0_AIN1],                                                # adc 5
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 6
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 7
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 8
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 9
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 10
        [ADS1118.MUX_AIN0_AIN1],                                                # adc 11
    ]

    # ====================== REAL CALIBRATION GAINS (cell 1..32) ======================
    # Paste your measured values here – one per cell, easy to update
    CELL_GAINS = [
        1.0, 1.0, 1.017,      # cell  1-3   (ADC 0)
        1.0, 1.01, 1.0,       # cell  4-6   (ADC 1)
        1.0, 1.0, 1.0,        # cell  7-9   (ADC 2)
        1.0, 1.0, 1.0,        # cell 10-12  (ADC 3)
        1.0, 0.964, 1.0,      # cell 13-15  (ADC 4)
        1.0,                  # cell 16     (ADC 5)
        0.971, 1.0, 1.0,      # cell 17-19  (ADC 6)
        1.025, 0.976, 1.023,  # cell 20-22  (ADC 7)
        0.978, 1.021, 0.98,   # cell 23-25  (ADC 8)
        0.942, 1.019, 0.982,  # cell 26-28  (ADC 9)
        0.948, 1.017, 0.984,  # cell 29-31  (ADC 10)
        0.953                 # cell 32     (ADC 11)
    ]

    GAIN_CONFIGS = []
    start = 0
    for cfg in MUX_CONFIGS:
        length = len(cfg)
        GAIN_CONFIGS.append(CELL_GAINS[start:start + length])
        start += length

    def __init__(self, spi):
        self.decoder = SN74HC154(
            enable_pin=HAL.CS_EN_PIN,
            a0_pin=HAL.SPI_CS0_PIN,
            a1_pin=HAL.SPI_CS1_PIN,
            a2_pin=HAL.SPI_CS2_PIN,
            a3_pin=HAL.SPI_CS3_PIN
        )
        self.adcs = [ADS1118(spi=spi) for _ in range(BMSadc.NUM_ADCS)]

        self.cell_offsets = [0]
        for cfg in BMSadc.MUX_CONFIGS[:-1]:
            self.cell_offsets.append(self.cell_offsets[-1] + len(cfg))

        self._adc_task = None          # background reading task
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
        """One interleaved read from every ADC"""
        for i in range(BMSadc.NUM_ADCS):
            self.decoder.select(i + 1)
            idx, vol = await self.adcs[i].read_scan()
            cell_idx = self.cell_offsets[i] + idx
            value = vol if (vol is not None and vol > 0.5) else -1.0
            bat.meas.set_vcell(cell_idx, value)
            self.decoder.deselect(i + 1)

    async def read_cell_voltages(self, bat: battery, rounds: int = 3):
        """Manual full refresh (still usable if you want one-shot reads)"""
        for _ in range(rounds):
            await self.read_one_round(bat)

    # ====================== BACKGROUND ASYNC TASK ======================
    def start_adc_task(self, bat: battery, interval_ms: int = 150):
        """
        Start a background task that continuously reads all cells.
        Call this AFTER start_all_continuous_scans().
        Non-blocking – returns immediately.
        """
        if self._adc_task is not None and not self._adc_task.done():
            self._adc_task.cancel()

        async def adc_reader():
            while True:
                try:
                    await self.read_cell_voltages(bat, rounds=3)   # 3 rounds = very fresh values
                    await asyncio.sleep_ms(interval_ms)
                except Exception as e:
                    self.log.error(f"[BMSadc] ADC task error: {e}")
                    await asyncio.sleep_ms(1000)   # back-off on error

        self._adc_task = asyncio.create_task(adc_reader())
        self.log.info(f"ADC background task started (update every {interval_ms} ms)")

    def stop_adc_task(self):
        """Stop the background reading task"""
        if self._adc_task is not None:
            self._adc_task.cancel()
            self._adc_task = None
            self.log.info("ADC background task stopped")

    def is_adc_task_running(self) -> bool:
        return self._adc_task is not None and not self._adc_task.done()