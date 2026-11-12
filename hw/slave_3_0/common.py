"""Shared setup for the slave 3.0.0.0 SKiDL design: KiCad paths, reference numbering, part helpers, nets."""
import os

KICAD = os.environ.get("KICAD_DIR", r"C:\Program Files\KiCad\10.0")
os.environ.setdefault("KICAD10_SYMBOL_DIR", os.path.join(KICAD, "share", "kicad", "symbols"))
os.environ.setdefault("KICAD10_FOOTPRINT_DIR", os.path.join(KICAD, "share", "kicad", "footprints"))

import builtins  # noqa: E402

from skidl import Net, Part, POWER, set_default_tool, KICAD10  # noqa: E402

set_default_tool(KICAD10)
NC = builtins.NC   # SKiDL 3 puts the no-connect net into builtins

N_CELLS = 16

FP = {
    "R0603": "Resistor_SMD:R_0603_1608Metric",
    "R0805": "Resistor_SMD:R_0805_2012Metric",
    "R1206": "Resistor_SMD:R_1206_3216Metric",
    "R2512": "Resistor_SMD:R_2512_6332Metric",
    "C0603": "Capacitor_SMD:C_0603_1608Metric",
    "C0805": "Capacitor_SMD:C_0805_2012Metric",
    "C1206": "Capacitor_SMD:C_1206_3216Metric",
    "C1210": "Capacitor_SMD:C_1210_3225Metric",
    "FUSE1206": "Fuse:Fuse_1206_3216Metric",
    "LED0603": "LED_SMD:LED_0603_1608Metric",
    "SMA": "Diode_SMD:D_SMA",
    "SOD123F": "Diode_SMD:D_SOD-123F",
    "TP": "TestPoint:TestPoint_Pad_D1.0mm",
}

# ----------------------------------------------------------------------
# Reference designators: one hundred block per sheet (R101.., R201.., ...)
# ----------------------------------------------------------------------
_base = [0]
_count = {}


def sheet(base):
    _base[0] = base


def _ref(prefix):
    key = (prefix, _base[0])
    _count[key] = _count.get(key, 0) + 1
    return f"{prefix}{_base[0] + _count[key]}"


def P(lib, name, prefix, value=None, footprint=None, note=None):
    ref = _ref(prefix)
    kw = {"ref": ref, "tag": ref}
    if footprint:
        kw["footprint"] = footprint
    p = Part(lib, name, **kw)
    if value is not None:
        p.value = value
    if note:
        p.fields["Note"] = note
    return p


def R(value, size="0603", note=None):
    return P("Device", "R", "R", value, FP["R" + size], note)


def C(value, size="0603", note=None):
    return P("Device", "C", "C", value, FP["C" + size], note)


def tp(net, name):
    t = P("Connector", "TestPoint", "TP", name, FP["TP"])
    t[1] += net
    return t


def two(part, a, b):
    """Connect pin 1 to a and pin 2 to b."""
    part[1] += a
    part[2] += b
    return part


def decouple(net, *values, size="0603"):
    for v in values:
        two(C(v, size), net, GND)


def power_net(name):
    n = Net(name)
    n.drive = POWER
    return n


# ----------------------------------------------------------------------
# Nets shared between sheets
# ----------------------------------------------------------------------
GND = power_net("GND")
VIN_HV = power_net("VIN_HV")
P5V = power_net("+5V")
P5VA = power_net("+5VA")
P3V3 = power_net("+3V3")
VBUS = power_net("VBUS")
VREF = power_net("VREF")

T = [Net(f"T{j}") for j in range(N_CELLS + 1)]        # cell taps at the connector
TF = [Net(f"T{j}_F") for j in range(N_CELLS + 1)]     # after the tap fuse
TM = [Net(f"T{j}_M") for j in range(N_CELLS + 1)]     # after the 1k measurement resistor

CELL_A = [Net(f"CELL_A{i}") for i in range(4)]
TAP_EN_n = Net("TAP_EN_n")
XFER_n = Net("XFER_n")
POL = Net("POL")
DISCH = Net("DISCH")

FC_HI = Net("FC_HI")
FC_GND = Net("FC_GND")
VSTR_DIV = Net("VSTR_DIV")

ADC_CS = Net("ADC_CS")
ADC_DIN = Net("ADC_DIN")
ADC_SCLK = Net("ADC_SCLK")
ADC_DOUT = Net("ADC_DOUT")
ADC_DRDY = Net("ADC_DRDY")

I2C_SDA = Net("I2C_SDA")
I2C_SCL = Net("I2C_SCL")
BAL_OE_n = Net("BAL_OE_n")

ACT_BAL_EN = Net("ACT_BAL_EN")
ACT_BAL_PWM = Net("ACT_BAL_PWM")
