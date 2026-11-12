# bringup.py - Hardware bring-up checks for slave HW 2.0.1.0
# Run from PC (libraries must be on the device):  make bringup PORT=COMx
# run() never switches balancing outputs on; bal_test() does that only when called explicitly.
import time
import asyncio
from machine import Pin, SoftSPI, SoftI2C
import onewire
import ds18x20
import hw
from lib.SN74HC154 import SN74HC154
from lib.ADS1118 import ADS1118, MUX_SE
from lib.PCA9685 import PCA9685

results = []


def report(name, ok, info=""):
    results.append((name, ok))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {info}")


def make_i2c():
    return SoftI2C(scl=Pin(hw.PIN_I2C_SCL), sda=Pin(hw.PIN_I2C_SDA), freq=100_000)


def make_spi(phase=hw.SPI_PHASE):
    return SoftSPI(baudrate=hw.SPI_BAUD, polarity=hw.SPI_POLARITY, phase=phase,
                   sck=Pin(hw.PIN_SPI_SCLK), mosi=Pin(hw.PIN_SPI_MOSI), miso=Pin(hw.PIN_SPI_MISO))


def make_demux():
    return SN74HC154(enable_pin=hw.PIN_DEMUX_EN, a0_pin=hw.PIN_DEMUX_A0, a1_pin=hw.PIN_DEMUX_A1,
                     a2_pin=hw.PIN_DEMUX_A2, a3_pin=hw.PIN_DEMUX_A3)


def make_adc(spi, demux, y):
    return ADS1118(spi, demux=demux, demux_output=y, pga=hw.ADS_PGA, dr=hw.ADS_DR)


def test_leds():
    usr = Pin(hw.PIN_LED_USR, Pin.OUT, value=1)
    err = Pin(hw.PIN_LED_ERR, Pin.OUT, value=1)
    for _ in range(3):
        usr(0); err(1); time.sleep_ms(250)
        usr(1); err(0); time.sleep_ms(250)
    usr(1); err(1)
    report("LEDs", True, "green/red should have blinked alternately 3x (visual check)")


def test_dip():
    pins = [Pin(p, Pin.IN, Pin.PULL_DOWN) for p in hw.PIN_STR_SEL]
    bits = [p.value() for p in pins]
    addr = sum(b << i for i, b in enumerate(bits))
    report("String address DIP", True, f"switch 1..4 = {bits} -> address {addr} (compare with DIP)")
    return addr


def test_onewire():
    ds = ds18x20.DS18X20(onewire.OneWire(Pin(hw.PIN_ONEWIRE)))
    roms = ds.scan()
    temps = []
    if roms:
        ds.convert_temp()
        time.sleep_ms(750)
        temps = ["%.2f" % ds.read_temp(r) for r in roms]
    report("DS18B20 bus", True, f"{len(roms)} sensor(s) {temps}")


def test_i2c():
    i2c = make_i2c()
    found = i2c.scan()
    report("I2C scan", all(a in found for a in hw.PCA_ADDR),
           f"found {[hex(a) for a in found]}, expected {[hex(a) for a in hw.PCA_ADDR]} (+0x70 all-call)")
    for a in hw.PCA_ADDR:
        if a not in found:
            continue
        pca = PCA9685(i2c, a, reset=False)   # read back state left by boot.py
        on = [ch for ch in range(16) if not pca.is_off(ch)]
        report(f"PCA9685 0x{a:02x} outputs off after boot", not on, f"channels not off: {on}")


def test_ads_presence():
    demux = make_demux()
    expected = {y for y, _, _ in hw.ADC_MAP}
    best = None
    for phase in (hw.SPI_PHASE, 1 - hw.SPI_PHASE):
        spi = make_spi(phase)
        echo = {y: make_adc(spi, demux, y).probe() for y in range(16)}
        n_ok = sum(1 for y in expected if echo[y][0])
        print(f"  SPI phase={phase}: {n_ok}/{len(expected)} ADS1118 answered")
        for y in range(16):
            tag = "ADC" if y in expected else "---"
            print(f"    Y{y:2d} {tag} ok={echo[y][0]} echo=0x{echo[y][1]:04x}")
        if best is None or n_ok > best[1]:
            best = (phase, n_ok)
    report("ADS1118 presence", best[1] == len(expected),
           f"best SPI phase={best[0]} ({best[1]}/{len(expected)}), expected phase={hw.SPI_PHASE}")
    return best[0]


async def read_all(phase):
    spi = make_spi(phase)
    demux = make_demux()
    print("  Y   taps(AIN0..3)            V_ain (V)                          V_tap (V)")
    for y, taps, ratios in hw.ADC_MAP:
        adc = make_adc(spi, demux, y)
        v_ain = []
        for ch in range(4):
            v_ain.append(await adc.read_voltage(MUX_SE[ch]))
        v_tap = [v * r for v, r in zip(v_ain, ratios)]
        t = await adc.read_temperature()
        print(f"  Y{y:<2} {str(taps):24} {' '.join('%7.4f' % v for v in v_ain)}   "
              f"{' '.join('%7.3f' % v for v in v_tap)}   die={t:.1f}C")


def bal_test(cell, seconds=2, duty=20):
    """Switch ONE balancing channel on (PhotoMOS + blue LED of that cell). Explicit call only."""
    pca = PCA9685(make_i2c(), hw.PCA_ADDR[(cell - 1) // 16], freq=hw.BAL_PWM_FREQ)
    try:
        pca.set_duty((cell - 1) % 16, duty)
        time.sleep(seconds)
    finally:
        pca.all_off()
    print(f"cell {cell}: balancing channel was on for {seconds}s at {duty}%")


def run():
    print("=== CALU BMS slave bring-up (HW %s) ===" % hw.HW_VERSION)
    test_leds()
    test_dip()
    test_onewire()
    test_i2c()
    phase = test_ads_presence()
    asyncio.run(read_all(phase))
    print("=== summary: %d/%d passed ===" % (sum(1 for _, ok in results if ok), len(results)))


if __name__ == "__main__":
    run()
