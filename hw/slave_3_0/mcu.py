"""Sheet MCU: ESP32-S3-WROOM-1-N8R8, reset/boot, USB-C, LEDs, address DIP, 1-Wire, pull resistors."""
from skidl import Net, subcircuit
from common import (NC, ACT_BAL_EN, ACT_BAL_PWM, ADC_CS, ADC_DIN, ADC_DOUT, ADC_DRDY, ADC_SCLK, BAL_OE_n, CELL_A,
                    DISCH, FP, GND, I2C_SCL, I2C_SDA, P, P3V3, POL, R, C, TAP_EN_n, VBUS, XFER_n, decouple,
                    sheet, tp, two)

# ESP32-S3-WROOM-1 module pin number per signal (KiCad symbol RF_Module:ESP32-S3-WROOM-1)
MODULE_PIN = {
    "IO0": 27, "IO1": 39, "IO2": 38, "IO3": 15, "IO4": 4, "IO5": 5, "IO6": 6, "IO7": 7, "IO8": 12, "IO9": 17,
    "IO10": 18, "IO11": 19, "IO12": 20, "IO13": 21, "IO14": 22, "IO15": 8, "IO16": 9, "IO17": 10, "IO18": 11,
    "IO21": 23, "IO35": 28, "IO36": 29, "IO37": 30, "IO38": 31, "IO39": 32, "IO40": 33, "IO41": 34, "IO42": 35,
    "IO45": 26, "IO46": 16, "IO47": 24, "IO48": 25, "RXD0": 36, "TXD0": 37,
    "USB_D-": 13, "USB_D+": 14, "EN": 3, "3V3": 2,
}
GND_PINS = (1, 40, 41)
UNUSED = ("IO3", "IO45", "IO46", "IO35", "IO36", "IO37")   # strapping pins / octal PSRAM


@subcircuit
def mcu(onewire):
    sheet(200)
    u = P("RF_Module", "ESP32-S3-WROOM-1", "U", "ESP32-S3-WROOM-1-N8R8")

    def io(name):
        return u[MODULE_PIN[name]]

    for pin in GND_PINS:
        u[pin] += GND
    io("3V3").connect(P3V3)
    decouple(P3V3, "10uF", "100nF", "100nF")
    for name in UNUSED:
        io(name).connect(NC)

    # Reset (EN) and boot (IO0)
    en, boot = Net("EN"), Net("BOOT")
    io("EN").connect(en)
    two(R("10k"), P3V3, en)
    two(C("1uF"), en, GND)
    two(P("Switch", "SW_Push", "SW", "RESET", "Button_Switch_SMD:SW_SPST_B3U-1000P"), en, GND)
    io("IO0").connect(boot)
    two(R("10k"), P3V3, boot)
    two(P("Switch", "SW_Push", "SW", "BOOT", "Button_Switch_SMD:SW_SPST_B3U-1000P"), boot, GND)

    # Signals to the other sheets
    signals = {
        "IO1": I2C_SDA, "IO2": I2C_SCL,
        "IO4": CELL_A[0], "IO5": CELL_A[1], "IO6": CELL_A[2], "IO7": CELL_A[3],
        "IO8": TAP_EN_n, "IO9": onewire,
        "IO10": ADC_CS, "IO11": ADC_DIN, "IO12": ADC_SCLK, "IO13": ADC_DOUT, "IO14": ADC_DRDY,
        "IO15": XFER_n, "IO16": POL, "IO17": DISCH, "IO18": BAL_OE_n,
        "IO21": ACT_BAL_EN, "IO38": ACT_BAL_PWM,
    }
    for name, net in signals.items():
        io(name).connect(net)

    # Safe states while the ESP32 is in reset: taps, transfer and balancing off, ADC deselected
    for net in (TAP_EN_n, XFER_n, BAL_OE_n, ADC_CS):
        two(R("10k"), P3V3, net)
    for net in (POL, DISCH):
        two(R("10k"), net, GND)
    for net in (ACT_BAL_EN, ACT_BAL_PWM):
        two(R("100k"), net, GND)
    two(R("4.7k"), P3V3, I2C_SDA)
    two(R("4.7k"), P3V3, I2C_SCL)

    # LEDs (active low)
    for name, color, res in (("IO39", "red", "820"), ("IO40", "green", "390")):
        led_net, anode = Net(f"LED_{'ERR' if color == 'red' else 'USR'}"), Net(f"LED_{color.upper()}_A")
        io(name).connect(led_net)
        two(R(res), P3V3, anode)
        led = P("Device", "LED", "D", color, FP["LED0603"])
        led["A"] += anode
        led["K"] += led_net

    # String address DIP: switch n connects pin n and pin 9-n, ON = 3V3
    dip = P("Switch", "SW_DIP_x04", "SW", "ADDR",
            "Button_Switch_THT:SW_DIP_SPSTx04_Slide_9.78x12.34mm_W7.62mm_P2.54mm")
    for bit, name in enumerate(("IO41", "IO42", "IO47", "IO48")):
        addr = Net(f"ADDR{bit}")
        dip[bit + 1] += P3V3
        dip[8 - bit] += addr
        io(name).connect(addr)
        two(R("100k"), addr, GND)

    # 1-Wire pull-up
    two(R("4.7k"), P3V3, onewire)

    # USB-C (device, USB 2.0)
    usb = P("Connector", "USB_C_Receptacle_USB2.0_16P", "J", "USB-C",
            "Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12")
    dp, dm, cc1, cc2, shield = Net("USB_D+"), Net("USB_D-"), Net("USB_CC1"), Net("USB_CC2"), Net("USB_SHIELD")
    for pin in ("A4", "A9", "B4", "B9"):
        usb[pin] += VBUS
    for pin in ("A1", "A12", "B1", "B12"):
        usb[pin] += GND
    usb["A6"] += dp
    usb["B6"] += dp
    usb["A7"] += dm
    usb["B7"] += dm
    usb["A5"] += cc1
    usb["B5"] += cc2
    usb["A8"] += NC
    usb["B8"] += NC
    usb["SH"] += shield
    two(R("5.1k"), cc1, GND)
    two(R("5.1k"), cc2, GND)
    two(R("1M"), shield, GND)
    two(C("4.7nF"), shield, GND)
    esd = P("Power_Protection", "PRTR5V0U2X", "D", "PRTR5V0U2X")
    esd["GND"] += GND
    esd["VCC"] += VBUS
    esd["I/O1"] += dp
    esd["I/O2"] += dm
    io("USB_D+").connect(dp)
    io("USB_D-").connect(dm)

    # UART0 test pads
    for name in ("TXD0", "RXD0"):
        n = Net(name)
        io(name).connect(n)
        tp(n, name)
