"""Create the initial KiCad PCB from the SKiDL circuit (run with KiCad's Python, needs pcbnew).

Footprints are linked to the generated schematic symbols (same deterministic UUIDs as sch_writer), so later
changes are applied in KiCad with "Update PCB from Schematic" (F8) and the layout is preserved.
An existing board is never overwritten.
"""
import builtins
import math
import os

import pcbnew

from sch_writer import uid

MM = pcbnew.FromMM


def kiid_path(project, sheet, ref):
    root = uid(project, "root")
    if sheet:
        s = uid(project, "sheet", sheet)
        return f"/{s}/{uid(project, f'/{root}/{s}', ref)}"
    return f"/{uid(project, f'/{root}', ref)}"


def _size(fp):
    try:
        bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
        if bb.GetWidth() > 0:
            return pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight()), bb
    except Exception:
        pass
    bb = fp.GetBoundingBox(False)
    return pcbnew.ToMM(bb.GetWidth()), pcbnew.ToMM(bb.GetHeight()), bb


def _shelf(items, width, gap=1.0):
    """items: list of (key, w, h). Returns {key: (x, y)} top-left positions and total height."""
    pos, x, y, row = {}, 0.0, 0.0, 0.0
    for key, w, h in items:
        if x > 0 and x + w > width:
            x, y, row = 0.0, y + row + gap, 0.0
        pos[key] = (x, y)
        x += w + gap
        row = max(row, h)
    return pos, y + row


def build_pcb(out_dir, project, fp_root, sheets, unconnected=None, holes_prefix="H"):
    path = os.path.join(out_dir, project + ".kicad_pcb")
    if os.path.exists(path):
        print(f"{path} exists - not overwritten (use Update PCB from Schematic in KiCad)")
        return None

    board = pcbnew.NewBoard(path)
    nets = {}

    def net_item(name):
        if name not in nets:
            nets[name] = pcbnew.NETINFO_ITEM(board, name)
            board.Add(nets[name])
        return nets[name]

    footprints = {}           # sheet -> list of (fp, w, h, bbox)
    holes = []
    for part in builtins.default_circuit.parts:
        lib, name = part.footprint.split(":")
        fp = pcbnew.FootprintLoad(os.path.join(fp_root, lib + ".pretty"), name)
        fp.SetFPID(pcbnew.LIB_ID(lib, name))
        fp.SetReference(part.ref)
        fp.SetValue(str(part.value))
        for key, val in part.fields.items():
            fp.SetField(key, str(val))
        sheet = part.hiertuple[1] if len(part.hiertuple) > 1 else ""
        fp.SetPath(pcbnew.KIID_PATH(kiid_path(project, sheet, part.ref)))
        board.Add(fp)
        for pin in part.pins:
            net = pin.net
            if net is None or type(net).__name__ == "NCNet":
                name_nc = (unconnected or {}).get((part.ref, pin.num))
                if not name_nc:
                    continue
                target = net_item(name_nc)
            else:
                target = net_item(net.name)
            pads = [p for p in fp.Pads() if p.GetNumber() == pin.num]
            if not pads:
                raise ValueError(f"{part.ref}: footprint {part.footprint} has no pad {pin.num}")
            for pad in pads:
                pad.SetNet(target)
        if part.ref.startswith(holes_prefix) and not part.pins:
            holes.append(fp)
            continue
        w, h, bb = _size(fp)
        footprints.setdefault(sheet, []).append((fp, w, h, bb))

    # Pack every sheet into a block, then the blocks into the board
    blocks = []
    for sheet in sheets:
        items = footprints.get(sheet, [])
        area = sum((w + 1) * (h + 1) for _, w, h, _ in items)
        width = max(max(w for _, w, _, _ in items) + 1, math.sqrt(area * 1.6))
        pos, height = _shelf([(i, w, h) for i, (_, w, h, _) in enumerate(items)], width)
        blocks.append((sheet, items, pos, width, height))
    total = sum((b[3] + 6) * (b[4] + 6) for b in blocks)
    board_w = math.sqrt(total * 1.5)
    bpos, board_h = _shelf([(i, b[3] + 6, b[4] + 6) for i, b in enumerate(blocks)], board_w, gap=0)
    board_w = max(bpos[i][0] + blocks[i][3] + 6 for i in bpos)
    margin = 8.0
    ox, oy = 50.0, 50.0

    for i, (sheet, items, pos, _, _) in enumerate(blocks):
        bx, by = bpos[i]
        group = pcbnew.PCB_GROUP(board)
        group.SetName(sheet)
        board.Add(group)
        for k, (fp, w, h, bb) in enumerate(items):
            px, py = pos[k]
            # move so that the courtyard's top-left corner lands on the packed position
            dx = pcbnew.ToMM(fp.GetPosition().x - bb.GetX())
            dy = pcbnew.ToMM(fp.GetPosition().y - bb.GetY())
            fp.SetPosition(pcbnew.VECTOR2I(MM(ox + margin + bx + 3 + px + dx), MM(oy + margin + by + 3 + py + dy)))
            group.AddItem(fp)

    width_mm = board_w + 2 * margin
    height_mm = board_h + 2 * margin
    rect = pcbnew.PCB_SHAPE(board)
    rect.SetShape(pcbnew.SHAPE_T_RECT)
    rect.SetStart(pcbnew.VECTOR2I(MM(ox), MM(oy)))
    rect.SetEnd(pcbnew.VECTOR2I(MM(ox + width_mm), MM(oy + height_mm)))
    rect.SetLayer(pcbnew.Edge_Cuts)
    rect.SetWidth(MM(0.1))
    board.Add(rect)
    for fp, (cx, cy) in zip(holes, ((4, 4), (width_mm - 4, 4), (4, height_mm - 4), (width_mm - 4, height_mm - 4))):
        fp.SetPosition(pcbnew.VECTOR2I(MM(ox + cx), MM(oy + cy)))

    pcbnew.SaveBoard(path, board)
    print(f"PCB written: {path} ({width_mm:.0f} x {height_mm:.0f} mm placeholder outline, {len(nets)} nets)")
    return path
