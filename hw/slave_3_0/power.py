"""Sheet POWER: string input protection, LM5164 100 V buck (+5V), +5VA filter, 3.3 V LDO, USB power path."""
from skidl import Net, subcircuit
from common import (NC, FP, GND, P, P3V3, P5V, P5VA, R, C, VBUS, VIN_HV, decouple, sheet, tp, two)


@subcircuit
def power():
    sheet(100)

    # Power connector J101: 1 = B+ (string top), 2 = B- (board GND, only ground connection of the board)
    j = P("Connector", "Screw_Terminal_01x02", "J", "B+/B-",
          "Connector_Phoenix_MSTB:PhoenixContact_MSTBA_2,5_2-G-5,08_1x02_P5.08mm_Horizontal")
    b_plus, b_plus_f = Net("B_PLUS"), Net("B_PLUS_F")
    j[1] += b_plus
    j[2] += GND

    two(P("Device", "Fuse", "F", "0.5A fast", FP["FUSE1206"]), b_plus, b_plus_f)
    d_rev = P("Diode", "SS110", "D", "SS110", FP["SMA"])            # reverse polarity protection
    d_rev["A"] += b_plus_f
    d_rev["K"] += VIN_HV
    tvs = P("Device", "D_Zener", "D", "SMAJ60A", FP["SMA"])          # unidirectional TVS, clamps < 100 V
    tvs["K"] += VIN_HV
    tvs["A"] += GND

    cbulk = P("Device", "C_Polarized", "C", "22uF 100V", "Capacitor_SMD:CP_Elec_8x10")
    two(cbulk, VIN_HV, GND)
    decouple(VIN_HV, "2.2uF 100V", "2.2uF 100V", size="1210")
    decouple(VIN_HV, "100nF 100V")

    # LM5164: 6..100 V in, 5 V out
    u = P("Regulator_Switching", "LM5164DDA", "U", "LM5164DDA")
    en, ron, fb, bst, sw = Net("BUCK_EN"), Net("BUCK_RON"), Net("BUCK_FB"), Net("BUCK_BST"), Net("BUCK_SW")
    u["VIN"] += VIN_HV
    u["GND"] += GND
    u["EP"] += GND
    u["EN/UVLO"] += en
    u["RON"] += ron
    u["FB"] += fb
    u["BST"] += bst
    u["SW"] += sw
    u["PGOOD"] += Net("BUCK_PGOOD")
    tp(u["PGOOD"].net, "PGOOD")

    two(R("1M", "0805", "UVLO divider, turn-on ~9 V: check LM5164 datasheet"), VIN_HV, en)
    two(R("180k", note="UVLO divider: check LM5164 datasheet"), en, GND)
    two(R("100k", note="sets switching frequency: calculate with WEBENCH"), ron, GND)
    two(C("2.2nF"), bst, sw)
    two(P("Device", "L", "L", "47uH", "Inductor_SMD:L_Bourns_SRR1260"), sw, P5V)
    two(R("316k", note="1%"), P5V, fb)       # Vout = 1.2 V * (1 + 316k/100k) = 4.99 V
    two(R("100k", note="1%"), fb, GND)
    decouple(P5V, "22uF 10V", "22uF 10V", size="1206")

    # USB power path for flashing without cells
    d_usb = P("Device", "D_Schottky", "D", "PMEG6020", FP["SOD123F"])
    d_usb["A"] += VBUS
    d_usb["K"] += P5V

    # +5VA for ADC, reference and buffer
    two(P("Device", "FerriteBead_Small", "FB", "600R@100MHz", "Inductor_SMD:L_0603_1608Metric"), P5V, P5VA)
    decouple(P5VA, "10uF", "100nF")

    # 3.3 V LDO
    ldo = P("Regulator_Linear", "TLV75733PDBV", "U", "TLV75733PDBV")
    ldo["IN"] += P5V
    ldo["EN"] += P5V
    ldo["GND"] += GND
    ldo["OUT"] += P3V3
    ldo["NC"] += NC
    decouple(P5V, "1uF")
    decouple(P3V3, "10uF", "100nF")

    for net, name in ((P5V, "+5V"), (P5VA, "+5VA"), (P3V3, "+3V3"), (GND, "GND"), (VIN_HV, "VIN_HV")):
        tp(net, name)
