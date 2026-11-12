# Slave 3.0.0.0 hardware (KiCad 10 + SKiDL)

The circuit is written in Python (SKiDL). Everything in `kicad/` except the PCB layout is generated.

| File | Content |
|---|---|
| `common.py` | KiCad paths, part helpers, reference numbering (one hundred block per sheet), shared nets |
| `power.py`, `mcu.py`, `cells.py`, `meas_mux.py`, `adc.py`, `balancing.py` | one schematic sheet each |
| `slave_3_0.py` | top level: ERC, netlist, schematic, checks, `--pcb` |
| `sch_writer.py` | writes the KiCad schematic (symbols + global labels) and the project file, verifies it |
| `build_pcb.py` | creates the initial PCB (only if none exists) |
| `kicad/` | generated KiCad project: open `slave_3_0.kicad_pro` |

Specification and design reasoning: [../CALU_BMS_Slave_3_0_0_0_schematic.md](../CALU_BMS_Slave_3_0_0_0_schematic.md)

## Workflow

```
make hw_tools   # once: SKiDL into KiCad's Python
make sch        # edit *.py, then regenerate netlist + schematic (verified against the netlist)
make erc        # KiCad ERC
make pcb        # first time only: initial PCB with all footprints, nets and net classes
make drc        # KiCad DRC incl. schematic <-> PCB parity
```

After a circuit change: `make sch`, then in KiCad **reload the schematic** (schematic editor: File → Revert, or
close it), then in the PCB editor **Tools → Update PCB from Schematic (F8)** and save (Ctrl+S).
F8 uses the schematic editor's data in memory: without the reload it applies the old circuit.
Footprints stay linked to their symbols (deterministic UUIDs), so the layout is kept.

Do not edit the generated `.kicad_sch` files in KiCad; change the Python source instead.
The PCB (`slave_3_0.kicad_pcb`) is edited in KiCad as usual.

## Schematic style

No wires: every pin has a global label with its net name. Unnamed nets are called `N$<n>`.
`make sch` exports KiCad's netlist of the generated schematic and compares it pin by pin with the SKiDL
netlist, so the drawing can't differ from the circuit.
