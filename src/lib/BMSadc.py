from lib.ADS1118_V2 import ADS1118
from lib.SN74HC154 import SN74HC154
from common.common import battery
from common.HAL import slave_hal as HAL
import asyncio

class BMSadc:
    NUM_ADCS = 12
    MUX_CONFIGS = [
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 0 → cells 0,1,2
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 1 → cells 3,4,5
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 2 → cells 6,7,8
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 3 → cells 9,10,11
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 4 → cells 12,13,14
        [ADS1118.MUX_AIN0_AIN1],                                                # adc 5 → cell 15 (only one)
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 6 → cells 16,17,18
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 7 → cells 19,20,21
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 8 → cells 22,23,24
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 9 → cells 25,26,27
        [ADS1118.MUX_AIN0_AIN1, ADS1118.MUX_AIN1_AIN3, ADS1118.MUX_AIN2_AIN3],  # adc 10 → cells 28,29,30
        [ADS1118.MUX_AIN0_AIN1],                                                # adc 11 → cell 31 (only one)
    ]

    # ====================== CALIBRATION GAINS ======================
    # Real measured gain correction for each cell (cell 1 = index 0)
    # Change these values any time you recalibrate
    CELL_GAINS = [
        1.0,   1.0,   1.017,  # cell 1-3   (ADC0)
        1.0,   1.01,  1.0,    # cell 4-6   (ADC1)
        1.0,   1.0,   1.0,    # cell 7-9   (ADC2)
        1.0,   1.0,   1.0,    # cell 10-12 (ADC3)
        1.0,   0.964, 1.0,    # cell 13-15 (ADC4)
        1.0,                  # cell 16    (ADC5)
        0.971, 1.0,   1.0,    # cell 17-19 (ADC6)
        1.025, 0.976, 1.023,  # cell 20-22 (ADC7)
        0.978, 1.021, 0.98,   # cell 23-25 (ADC8)
        0.942, 1.019, 0.982,  # cell 26-28 (ADC9)
        0.948, 1.017, 0.984,  # cell 29-31 (ADC10)
        0.953                 # cell 32    (ADC11)
    ]

    # Auto-build GAIN_CONFIGS from the flat list (no manual counting!)
    GAIN_CONFIGS = []
    start = 0
    for cfg in MUX_CONFIGS:
        length = len(cfg)
        GAIN_CONFIGS.append(CELL_GAINS[start : start + length])
        start += length
        
    def __init__(self,spi):
        self.decoder = SN74HC154(enable_pin=HAL.CS_EN_PIN, a0_pin=HAL.SPI_CS0_PIN, a1_pin=HAL.SPI_CS1_PIN, a2_pin=HAL.SPI_CS2_PIN, a3_pin=HAL.SPI_CS3_PIN)
        self.adcs = [ADS1118(spi=spi) for _ in range(BMSadc.NUM_ADCS)]
        self.cell_offsets = [0]
        for cfg in BMSadc.MUX_CONFIGS[:-1]:
            self.cell_offsets.append(self.cell_offsets[-1] + len(cfg))

    async def start_all_continuous_scans(self):
        """Call once at startup"""
        for i in range(BMSadc.NUM_ADCS):
            self.decoder.select(i + 1)     
            await self.adcs[i].start_continuous_scan(mux_list=BMSadc.MUX_CONFIGS[i], gain_list=BMSadc.GAIN_CONFIGS[i])
            self.decoder.deselect(i + 1)
            await asyncio.sleep_ms(1)
    
    async def _read_one_round(self, bat:battery):
        for i in range(BMSadc.NUM_ADCS):
            self.decoder.select(i + 1)
            idx, vol = await self.adcs[i].read_scan()
            cell_idx = self.cell_offsets[i] + idx
            value = vol if (vol is not None and vol > 0.5) else -1.0
            bat.meas.set_vcell(cell_idx, value)
            self.decoder.deselect(i + 1)

    async def read_cell_voltages(self, bat: battery, rounds: int = 3):
        for _ in range(rounds):
            await self.read_one_round(bat)
