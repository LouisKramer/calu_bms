"""Sheet CELLS: cell tap connector, tap fuses, measurement series resistors, string divider,
active balancer header and DS18B20 connectors."""
from skidl import Net, subcircuit
from common import (NC, ACT_BAL_EN, ACT_BAL_PWM, FP, GND, N_CELLS, P, P3V3, R, C, T, TF, TM, VSTR_DIV, sheet, two)

TERM = "TerminalBlock_Degson:TerminalBlock_Degson_DG250-3.5-{n:02d}P_1x{n:02d}_P3.50mm_45Degree"


@subcircuit
def cells(onewire):
    sheet(300)

    # J301 cell taps: pin j+1 = Tj (T0 = B-, Tn = + of cell n). T0 is NOT connected to board GND:
    # the flying capacitor measures floating, and the supply current must return via J101 only.
    j = P("Connector_Generic", "Conn_01x18", "J", "CELL TAPS", TERM.format(n=18),
          note="placeholder footprint, use a pluggable 3.5 mm header (e.g. 15EDGRC-3.5-18P)")
    for k in range(N_CELLS + 1):
        j[k + 1] += T[k]
        two(P("Device", "Fuse", "F", "1A fast", FP["FUSE1206"]), T[k], TF[k])
        two(R("1k", "1206", "pulse-proof (anti-surge)"), TF[k], TM[k])
    j[18] += NC

    # String voltage divider for the plausibility check (ratio 16.3 -> 58.4 V = 3.58 V)
    a, b = Net("VSTR_A"), Net("VSTR_B")
    two(R("510k", "0805"), TF[N_CELLS], a)
    two(R("510k", "0805"), a, b)
    two(R("510k", "0805"), b, VSTR_DIV)
    two(R("100k", note="0.1%"), VSTR_DIV, GND)
    two(C("100nF"), VSTR_DIV, GND)

    # J302 active balancer header, pin compatible with 2.0.1.0 U18
    jb = P("Connector_Generic", "Conn_01x20", "J", "ACT BAL", TERM.format(n=20),
           note="placeholder footprint, use a pluggable 3.5 mm header (e.g. 15EDGRC-3.5-20P)")
    for k in range(N_CELLS + 1):
        jb[k + 1] += TF[k]
    jb[18] += NC
    jb[19] += ACT_BAL_EN
    jb[20] += ACT_BAL_PWM

    # DS18B20 connectors J303..J306: 1 = data, 2 = 3V3, 3 = GND
    ow = Net("ONEWIRE_BUS")
    two(R("100"), onewire, ow)
    for _ in range(4):
        cn = P("Connector_Generic", "Conn_01x03", "J", "DS18B20", TERM.format(n=3))
        cn[1] += ow
        cn[2] += P3V3
        cn[3] += GND
