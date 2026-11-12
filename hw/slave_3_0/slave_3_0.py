"""CALU BMS Slave 3.0.0.0 - top level.

Run with KiCad's Python (make sch):
    "C:/Program Files/KiCad/10.0/bin/python.exe" hw/slave_3_0/slave_3_0.py
Writes kicad/slave_3_0.net, the schematic (kicad/slave_3_0*.kicad_sch) and an ERC report.
"""
import builtins
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from common import FP, KICAD, N_CELLS, P, sheet  # noqa: E402
from skidl import ERC, Net, generate_netlist  # noqa: E402
from sch_writer import verify_schematic, write_project, write_schematic  # noqa: E402
from power import power  # noqa: E402
from mcu import mcu  # noqa: E402
from cells import cells  # noqa: E402
from meas_mux import meas_mux  # noqa: E402
from adc import adc  # noqa: E402
from balancing import balancing  # noqa: E402

OUT = os.path.join(HERE, "kicad")
NAME = "slave_3_0"
KICAD_CLI = os.path.join(KICAD, "bin", "kicad-cli.exe")
SHEETS = ("power", "mcu", "cells", "meas_mux", "adc", "balancing")
# Clearance >= 1 mm for everything that carries cell or string voltage
NETCLASS_PATTERNS = ([("HV", p) for p in ("T?", "T??", "T?_F", "T??_F", "T?_M", "T??_M", "BUS_A", "BUS_B",
                                           "VIN_HV", "B_PLUS*", "VSTR_A", "VSTR_B")]
                     + [("BAL", "BAL_R*")])


def mechanical():
    sheet(900)
    for _ in range(4):
        P("Mechanical", "MountingHole", "H", "M3", "MountingHole:MountingHole_3.2mm_M3")


def check_footprints():
    root = os.path.join(KICAD, "share", "kicad", "footprints")
    missing = []
    for part in builtins.default_circuit.parts:
        fp = part.footprint
        if not fp:
            missing.append(f"{part.ref}: no footprint")
            continue
        lib, name = fp.split(":")
        if not os.path.isfile(os.path.join(root, lib + ".pretty", name + ".kicad_mod")):
            missing.append(f"{part.ref}: {fp}")
    return missing


def check_nets(expected):
    """Every listed net must still exist on its own (a wrong pin match would merge nets silently)."""
    names = {}
    for net in builtins.default_circuit.nets:
        if net.pins:
            names.setdefault(net.name, 0)
            names[net.name] += 1
    return [n for n in expected if n not in names]


def main():
    onewire, ntc_div = Net("ONEWIRE"), Net("NTC_DIV")
    power(tag="power")
    mcu(onewire, tag="mcu")
    cells(onewire, tag="cells")
    meas_mux(tag="meas_mux")
    adc(ntc_div, tag="adc")
    balancing(ntc_div, tag="balancing")
    mechanical()

    os.makedirs(OUT, exist_ok=True)
    os.chdir(OUT)
    ERC()
    generate_netlist(file_=NAME + ".net")

    problems = check_footprints()
    expected = (["GND", "+5V", "+5VA", "+3V3", "VIN_HV", "VREF", "BUS_A", "BUS_B", "FC_HI", "FC_GND",
                 "TAP_EN_n", "XFER_n", "POL", "DISCH", "BAL_OE_n", "I2C_SDA", "I2C_SCL"]
                + [f"T{j}_M" for j in range(N_CELLS + 1)] + [f"SEL{i}_n" for i in range(N_CELLS)]
                + [f"BAL_DRV{n}" for n in range(1, N_CELLS + 1)])
    problems += [f"net {n} missing or merged" for n in check_nets(expected)]
    print(f"{len(builtins.default_circuit.parts)} parts, {len([n for n in builtins.default_circuit.nets if n.pins])} nets")
    if problems:
        print("PROBLEMS:\n  " + "\n  ".join(problems))
        sys.exit(1)

    if "--no-sch" in sys.argv:
        return
    write_schematic(OUT, NAME, "CALU BMS Slave 3.0.0.0", SHEETS)
    write_project(OUT, NAME, NETCLASS_PATTERNS)
    sch_problems, unconnected = verify_schematic(OUT, NAME, KICAD_CLI, NAME + ".net")
    if sch_problems:
        print("SCHEMATIC DOES NOT MATCH NETLIST:\n  " + "\n  ".join(sch_problems[:30]))
        sys.exit(1)
    print("schematic written and verified against the netlist")
    if "--pcb" in sys.argv:
        from build_pcb import build_pcb
        build_pcb(OUT, NAME, os.path.join(KICAD, "share", "kicad", "footprints"), SHEETS, unconnected)


if __name__ == "__main__":
    main()
