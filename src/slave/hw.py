# hw.py - Hardware description of CALU BMS Slave HW 2.0.1.0
# Source: hw/CALU_BMS_Slave_2_0_1_0.epro2 (PCB netlist)
from micropython import const
from lib.cell_monitor import TAP_GND, TAP_B_BOT

HW_VERSION = "2.0.1.0"

# ----------------------------------------------------------------------
# GPIO
# ----------------------------------------------------------------------
PIN_SPI_SCLK = const(6)
PIN_SPI_MOSI = const(7)
PIN_SPI_MISO = const(15)   # 1k pull-up on board

PIN_DEMUX_A0 = const(16)
PIN_DEMUX_A1 = const(17)
PIN_DEMUX_A2 = const(18)
PIN_DEMUX_A3 = const(8)
PIN_DEMUX_EN = const(10)   # SN74HC154 G1, active low (no pull-up on board)

PIN_I2C_SCL = const(11)    # 1k pull-up to 3V3, PCA9685 supplied from +5V
PIN_I2C_SDA = const(3)

PIN_ONEWIRE = const(9)     # DS18B20 bus on CN2..CN5, 4.7k pull-up on board

PIN_LED_USR = const(40)    # green, active low
PIN_LED_ERR = const(39)    # red, active low

PIN_STR_SEL = (41, 42, 2, 38)  # DIP SW1 switch 1..4 = address bit 0..3, ON = 3V3 -> internal pull-down

PIN_ACT_BAL_EN = const(47)     # to external active balancer (U18/U36 pin 19), not used yet
PIN_ACT_BAL_PWM = const(48)    # U18/U36 pin 20

# ----------------------------------------------------------------------
# SPI / ADS1118
# ----------------------------------------------------------------------
SPI_BAUD = const(1_000_000)
SPI_POLARITY = const(0)    # ADS1118: SPI mode 1
SPI_PHASE = const(1)
ADS_PGA = const(2)         # +-2.048 V, all divided taps stay below ~1.94 V at 3.65 V/cell
ADS_DR = const(4)          # 128 SPS

# (demux output, tap on AIN0..AIN3, divider ratio AIN0..AIN3)
# Tap n = BAn+ (1..32), TAP_GND = BA1- (board GND), TAP_B_BOT = BA17-.
# ratio = (R_top + 10k) / 10k  ->  V_tap = V_ain * ratio
# The ratios are the E24 values chosen by main:tools/resisitor_calc.py (ideal 2*n, i.e. 2 V at
# 4 V/cell); using them directly equals applying its precalculated correction gain (ideal / actual).
#
# Every tap is measured single-ended (AINx vs GND). A differential pair such as AIN0-AIN1 is NOT
# proportional to the cell voltage, because both inputs use different ratios:
#   d = V_tap(n)/r_n - V_tap(n-1)/r_(n-1)  (0 V for two equal cells on taps 1/2)
#   V_cell(n) = r_n*d + (r_n - r_(n-1)) * V_ain(n-1)  -> needs the absolute lower input anyway.
# Chaining differentials from GND was evaluated and is worse here: 710 kOhm input impedance at
# +-0.256 V (~2.7 % error on every difference) and accumulating offsets.
ADC_MAP = (
    # string A (cells 1..16)
    (1,  (TAP_GND, 1, 3, 2),        (1.0, 2.0, 6.1, 4.0)),       # U72
    (2,  (3, 4, 6, 5),              (6.1, 8.0, 12.0, 10.1)),     # U73
    (3,  (6, 7, 9, 8),              (12.0, 14.0, 18.0, 16.0)),   # U74
    (4,  (9, 10, 12, 11),           (18.0, 20.0, 24.0, 22.0)),   # U75
    (5,  (12, 13, 15, 14),          (24.0, 26.0, 30.0, 27.0)),   # U76
    (6,  (15, 16, 16, TAP_GND),     (30.0, 32.0, 32.0, 1.0)),    # U77
    # string B (cells 17..32)
    (15, (TAP_B_BOT, 17, 19, 18),   (32.0, 33.0, 38.0, 36.0)),   # U66
    (14, (19, 20, 22, 21),          (38.0, 41.0, 45.0, 41.0)),   # U67
    (13, (22, 23, 25, 24),          (45.0, 45.0, 49.0, 49.0)),   # U68
    (12, (25, 26, 28, 27),          (49.0, 49.0, 55.0, 55.0)),   # U69
    (11, (28, 29, 31, 30),          (55.0, 55.0, 61.0, 61.0)),   # U70
    (10, (31, 32, 32, TAP_B_BOT),   (61.0, 61.0, 61.0, 32.0)),   # U71
)
NR_ADC_STRING_A = const(6)
# Above ~3.85 V/cell the BA26+ input (ratio 49) saturates -> front end is sized for LFP.

# ----------------------------------------------------------------------
# Balancing (PCA9685 -> BSS138 -> GAQY211 PhotoMOS -> 5.1R 2512 across the cell)
# ----------------------------------------------------------------------
PCA_ADDR = (0x40, 0x41)    # U5: cells 1..16, U23: cells 17..32 (channel = (cell-1) % 16)
BAL_PWM_FREQ = const(100)
BAL_RESISTOR_OHM = 5.1
BAL_RESISTOR_RATED_W = 1.0   # Yageo RC2512, without extra cooling

# ----------------------------------------------------------------------
# Cell configuration limits
# ----------------------------------------------------------------------
# The LM2596HVS-5.0 is fed from BA16+, so string A must always reach BA16+ (unused taps bridged).
# 4 cells keep >= 10 V even at 2.5 V/cell (LFP empty); the LM2596 needs >= ~7 V.
MIN_CELLS_A = const(4)
