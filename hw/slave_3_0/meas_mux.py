"""Sheet MEAS_MUX: flying-capacitor multiplexer.

17 tap PhotoMOS (even taps -> BUS_A, odd taps -> BUS_B) selected by a 74HCT154 with BAT54A diode-OR:
decoder output Y(k-1) turns on exactly taps k-1 and k (cell k). The 74HCT138 drives the transfer
H-bridge and is only enabled while TAP_EN_n is high (all tap switches off).
"""
from skidl import Net, subcircuit
from common import (NC, CELL_A, DISCH, FC_GND, FC_HI, GND, N_CELLS, P, P5V, POL, R, TAP_EN_n, TM, XFER_n,
                    decouple, sheet, two)

SSR_MEAS = ("Relay_SolidState", "AQY280S")   # 350 V, 25 ohm, SO-4: sees up to the full string voltage


def photomos(led_cathode, out_a, out_b, value="AQY280S"):
    """PhotoMOS with LED anode via 560R from +5V (5 mA), output between out_a and out_b."""
    k = P(*SSR_MEAS, "K", value)
    anode = Net()
    two(R("560"), P5V, anode)
    k[1] += anode
    k[2] += led_cathode
    k[4] += out_a
    k[3] += out_b
    return k


def diode_or(cathode_net, out1, out2):
    """BAT54A: common anode (pin 3) on the LED cathode, cathodes to two active-low decoder outputs."""
    d = P("Diode", "BAT54A", "D", "BAT54A")
    d[3] += cathode_net
    d[1] += out1
    d[2] += out2


@subcircuit
def meas_mux():
    sheet(400)
    bus_a, bus_b = Net("BUS_A"), Net("BUS_B")

    # Cell select decoder (74HCT154 = 74LS154 symbol, HCT for 3.3 V inputs at 5 V supply). Pin numbers:
    # A0..A3 = 23, 22, 21, 20; E0 = 18, E1 = 19; S0..S10 = 1..11, S11..S15 = 13..17; GND = 12, VCC = 24
    dec = P("74xx", "74LS154", "U", "74HCT154", "Package_SO:SOIC-24W_7.5x15.4mm_P1.27mm")
    sel = [Net(f"SEL{i}_n") for i in range(N_CELLS)]
    for i, pin in enumerate((23, 22, 21, 20)):
        dec[pin] += CELL_A[i]
    dec[18] += TAP_EN_n
    dec[19] += GND
    dec[24] += P5V
    dec[12] += GND
    for i, pin in enumerate(list(range(1, 12)) + list(range(13, 18))):
        dec[pin] += sel[i]
    decouple(P5V, "100nF")

    # Tap switches
    for j in range(N_CELLS + 1):
        bus = bus_a if j % 2 == 0 else bus_b
        if j == 0:
            cathode = sel[0]
        elif j == N_CELLS:
            cathode = sel[N_CELLS - 1]
        else:
            cathode = Net(f"TAPK{j}")
            diode_or(cathode, sel[j - 1], sel[j])
        photomos(cathode, TM[j], bus)

    # Flying capacitor: polypropylene film only
    two(P("Device", "C", "C", "1uF MKP 63V", "Capacitor_THT:C_Rect_L13.0mm_W5.0mm_P10.00mm_FKS3_FKP3_MKS4",
          note="polypropylene film (MKP), no ceramic"), bus_a, bus_b)

    # Transfer select: Y0 = even cell, Y1 = odd cell, Y2 = discharge
    # Pin numbers: A0..A2 = 1..3, ~E0 = 4, ~E1 = 5, E2 = 6, ~Y0..~Y7 = 15..9, 7; GND = 8, VCC = 16
    xs = P("74xx", "74HCT138", "U", "74HCT138", "Package_SO:SOIC-16_3.9x9.9mm_P1.27mm")
    y = [Net(f"XY{i}_n") for i in range(3)]
    xs[1] += POL
    xs[2] += DISCH
    xs[3] += GND
    xs[6] += TAP_EN_n          # E2 (active high): only while the tap decoder is disabled
    xs[4] += XFER_n            # ~E0
    xs[5] += GND               # ~E1
    xs[16] += P5V
    xs[8] += GND
    xs[15] += y[0]
    xs[14] += y[1]
    xs[13] += y[2]
    for pin in (12, 11, 10, 9, 7):
        xs[pin] += NC
    decouple(P5V, "100nF")

    photomos(y[0], bus_a, FC_HI)                    # A_P: even cell, BUS_A positive
    photomos(y[1], bus_b, FC_HI)                    # B_P: odd cell, BUS_B positive
    ag, bg = Net("XK_AG"), Net("XK_BG")
    diode_or(ag, y[1], y[2])
    photomos(ag, bus_a, FC_GND)                     # A_G: odd cell, discharge
    diode_or(bg, y[0], y[2])
    photomos(bg, bus_b, FC_GND)                     # B_G: even cell, discharge
