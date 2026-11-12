"""Sheet BALANCING: PCA9685 (3.3 V, OE = hardware kill) driving 16 PhotoMOS, 2x 33R 2512 per cell (~200 mA),
NTC between the bleed resistors."""
from skidl import Net, subcircuit
from common import (BAL_OE_n, FP, GND, I2C_SCL, I2C_SDA, N_CELLS, P, P3V3, R, C, TF, VREF, decouple, sheet, two)

# PCA9685PW pins: A0..A4 = 1..5, A5 = 24, LED0..LED7 = 6..13, VSS = 14, LED8..LED15 = 15..22,
# ~OE = 23, EXTCLK = 25, SCL = 26, SDA = 27, VDD = 28
LED_PIN = list(range(6, 14)) + list(range(15, 23))


@subcircuit
def balancing(ntc_div):
    sheet(600)
    pca = P("Driver_LED", "PCA9685PW", "U", "PCA9685PW")
    for pin in (1, 2, 3, 4, 5, 24, 14, 25):          # address 0x40, VSS, EXTCLK
        pca[pin] += GND
    pca[23] += BAL_OE_n
    pca[26] += I2C_SCL
    pca[27] += I2C_SDA
    pca[28] += P3V3
    decouple(P3V3, "10uF", "100nF")

    for n in range(1, N_CELLS + 1):
        drv, led_a, ind_a, bl = Net(f"BAL_DRV{n}"), Net(), Net(), Net(f"BAL_R{n}")
        pca[LED_PIN[n - 1]] += drv

        # PhotoMOS LED ~5 mA from the totem-pole output, indicator LED ~1 mA
        two(R("390"), drv, led_a)
        k = P("Relay_SolidState", "AQY282GS", "K", "AQY282GS")
        k[1] += led_a
        k[2] += GND
        two(R("1k"), drv, ind_a)
        ind = P("Device", "LED", "D", "blue", FP["LED0603"])
        ind["A"] += ind_a
        ind["K"] += GND

        # Bleed path across cell n: T(n-1)_F -> PhotoMOS -> 2x 33R parallel -> Tn_F
        k[4] += TF[n - 1]
        k[3] += bl
        two(R("33", "2512", "1 W"), bl, TF[n])
        two(R("33", "2512", "1 W"), bl, TF[n])

    # Bleed resistor temperature (ratiometric to VREF), place RT between the bleed resistors
    two(R("10k", note="0.1%"), VREF, ntc_div)
    two(P("Device", "Thermistor_NTC", "RT", "10k B3950", FP["R0603"]), ntc_div, GND)
    two(C("100nF"), ntc_div, GND)
