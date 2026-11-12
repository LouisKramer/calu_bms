"""Sheet ADC: zero-drift buffer, ADS1220 (24 bit, PGA bypassed) with REF5040 4.096 V reference,
string voltage and bleed-resistor NTC on AIN2/AIN3."""
from skidl import Net, subcircuit
from common import (NC, ADC_CS, ADC_DIN, ADC_DOUT, ADC_DRDY, ADC_SCLK, FC_GND, FC_HI, GND, P, P3V3, P5VA, R, C, VREF,
                    VSTR_DIV, decouple, sheet, tp, two)


@subcircuit
def adc(ntc_div):
    sheet(500)
    buf_in, buf_out, ain0, ain1 = Net("BUF_IN"), Net("BUF_OUT"), Net("AIN0_F"), Net("AIN1_F")

    # FC_GND joins GND at one point next to the ADC (net tie = star point in the layout)
    nt = P("Device", "NetTie_2", "NT", "STAR", "NetTie:NetTie-2_SMD_Pad0.5mm")
    two(nt, FC_GND, GND)

    # Unity-gain buffer, 10k limits fault current into the input clamp diodes
    two(R("10k"), FC_HI, buf_in)
    op = P("Amplifier_Operational", "OPA333xxDBV", "U", "OPA333AIDBV")
    op[3] += buf_in     # +IN
    op[4] += buf_out    # -IN
    op[1] += buf_out    # OUT
    op[5] += P5VA
    op[2] += GND
    decouple(P5VA, "100nF")

    two(R("100"), buf_out, ain0)
    two(C("10nF", note="C0G"), ain0, GND)
    two(R("100"), FC_GND, ain1)
    two(C("10nF", note="C0G"), ain1, GND)

    # ADS1220 pins: 1 SCLK, 2 ~CS, 3 CLK, 4 DGND, 5 AVSS, 6 AIN3, 7 AIN2, 8 REFN0, 9 REFP0, 10 AIN1,
    # 11 AIN0, 12 AVDD, 13 DVDD, 14 ~DRDY, 15 DOUT, 16 DIN
    u = P("Analog_ADC", "ADS1220xPW", "U", "ADS1220IPW")
    for pin, net in ((1, ADC_SCLK), (2, ADC_CS), (3, GND), (4, GND), (5, GND), (6, ntc_div), (7, VSTR_DIV),
                     (8, GND), (9, VREF), (10, ain1), (11, ain0), (12, P5VA), (13, P3V3), (14, ADC_DRDY),
                     (15, ADC_DOUT), (16, ADC_DIN)):
        u[pin] += net
    decouple(P5VA, "1uF", "100nF")
    decouple(P3V3, "100nF")

    # REF5040: 1 DNC, 2 VIN, 3 TEMP, 4 GND, 5 TRIM/NR, 6 VOUT, 7 NC, 8 DNC
    ref = P("Reference_Voltage", "REF5040ID", "U", "REF5040ID")
    nr = Net("VREF_NR")
    ref[2] += P5VA
    ref[4] += GND
    ref[5] += nr
    ref[6] += VREF
    for pin in (1, 3, 7, 8):
        ref[pin] += NC
    two(C("1uF"), nr, GND)
    decouple(P5VA, "1uF")
    decouple(VREF, "10uF", "100nF", size="0805")

    tp(VREF, "VREF")
    tp(FC_HI, "FC_HI")
    tp(buf_out, "BUF_OUT")
