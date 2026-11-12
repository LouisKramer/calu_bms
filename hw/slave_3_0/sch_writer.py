"""Write a KiCad schematic from the SKiDL circuit.

Every symbol is copied from the KiCad library and every pin gets a global label with its SKiDL net name
(or a no-connect flag). No wires are drawn, so the drawn connectivity is exactly the SKiDL netlist;
verify_schematic() proves it by comparing KiCad's own netlist export with the SKiDL netlist.
UUIDs are derived from the references, so the PCB stays linked when the schematic is regenerated.
"""
import builtins
import copy
import json
import os
import re
import subprocess
import uuid

NS = uuid.UUID("6f1c2b0e-8a7d-4c1e-9a55-3c0b6b2a9e11")
GRID = 2.54
FONT = 1.27
CHAR_W = 1.1          # approx. width of one label character in mm
LABEL_PAD = 3.0       # label shape + gap
FORMAT_VERSION = "20250114"
PAPERS = (("A3", 420, 297), ("A2", 594, 420), ("A1", 841, 594), ("A0", 1189, 841))


def uid(*parts):
    return str(uuid.uuid5(NS, "/".join(parts)))


# ----------------------------------------------------------------------
# Minimal S-expression parser / writer (strings are kept raw, so they round-trip unchanged)
# ----------------------------------------------------------------------
class Q(str):
    """Quoted string atom."""


_TOK = re.compile(r'\s*(\(|\)|"(?:\\.|[^"\\])*"|[^\s()"]+)')


def parse(text):
    stack = [[]]
    for m in _TOK.finditer(text):
        t = m.group(1)
        if t == "(":
            stack.append([])
        elif t == ")":
            node = stack.pop()
            stack[-1].append(node)
        elif t.startswith('"'):
            stack[-1].append(Q(t[1:-1]))
        else:
            stack[-1].append(t)
    return stack[0][0]


def _atom(e):
    if isinstance(e, Q):
        return f'"{e}"'
    if isinstance(e, float):
        return f"{e:.4f}".rstrip("0").rstrip(".")
    return str(e)


def dump(x, ind=0):
    if not isinstance(x, list):
        return _atom(x)
    if all(not isinstance(e, list) for e in x):
        return "(" + " ".join(_atom(e) for e in x) + ")"
    out = "(" + _atom(x[0])
    for e in x[1:]:
        out += ("\n" + "\t" * (ind + 1) + dump(e, ind + 1)) if isinstance(e, list) else " " + _atom(e)
    return out + ")"


def child(node, key):
    for e in node[1:]:
        if isinstance(e, list) and e and e[0] == key:
            return e
    return None


def children(node, key):
    return [e for e in node[1:] if isinstance(e, list) and e and e[0] == key]


def esc(s):
    return Q(str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n"))


# ----------------------------------------------------------------------
# Library access
# ----------------------------------------------------------------------
_libs = {}


def _lib(name):
    if name not in _libs:
        path = os.path.join(os.environ["KICAD10_SYMBOL_DIR"], name + ".kicad_sym")
        tree = parse(open(path, encoding="utf-8").read())
        _libs[name] = {e[1]: e for e in children(tree, "symbol")}
    return _libs[name]


def flat_symbol(lib, name):
    """Library symbol with 'extends' resolved, named like the library entry."""
    sym = _lib(lib)[name]
    ext = child(sym, "extends")
    if not ext:
        return copy.deepcopy(sym)
    parent = flat_symbol(lib, ext[1])
    pname = parent[1]
    s = copy.deepcopy(parent)
    s[1] = Q(name)
    for e in children(s, "symbol"):
        if e[1].startswith(pname + "_"):
            e[1] = Q(name + e[1][len(pname):])
    props = {p[1]: p for p in children(sym, "property")}
    for i, e in enumerate(s):
        if isinstance(e, list) and e and e[0] == "property" and e[1] in props:
            s[i] = copy.deepcopy(props.pop(e[1]))
    first_sub = next(i for i, e in enumerate(s) if isinstance(e, list) and e and e[0] == "symbol")
    for p in props.values():
        s.insert(first_sub, copy.deepcopy(p))
    return s


def _unit_style(sub_name):
    m = re.match(r".*_(\d+)_(\d+)$", sub_name)
    return int(m.group(1)), int(m.group(2))


def symbol_geometry(sym):
    """Pins {number: (x, y, angle, type, hidden)} and body bbox of unit 1, symbol coords (y up)."""
    pins, xs, ys = {}, [], []
    for sub in children(sym, "symbol"):
        unit, style = _unit_style(sub[1])
        if unit not in (0, 1) or style not in (0, 1):
            continue
        for g in sub[1:]:
            if not isinstance(g, list):
                continue
            if g[0] == "pin":
                at = child(g, "at")
                hidden = child(g, "hide") is not None or "hide" in g
                pins[child(g, "number")[1]] = (float(at[1]), float(at[2]), int(float(at[3])) % 360, g[1], hidden)
            elif g[0] == "rectangle":
                for k in ("start", "end"):
                    p = child(g, k)
                    xs.append(float(p[1]))
                    ys.append(float(p[2]))
            elif g[0] in ("polyline", "bezier"):
                for p in children(child(g, "pts"), "xy"):
                    xs.append(float(p[1]))
                    ys.append(float(p[2]))
            elif g[0] == "circle":
                c, r = child(g, "center"), float(child(g, "radius")[1])
                xs += [float(c[1]) - r, float(c[1]) + r]
                ys += [float(c[2]) - r, float(c[2]) + r]
            elif g[0] == "arc":
                for k in ("start", "mid", "end"):
                    p = child(g, k)
                    xs.append(float(p[1]))
                    ys.append(float(p[2]))
    for x, y, *_ in pins.values():
        xs.append(x)
        ys.append(y)
    if not xs:
        xs, ys = [-1.27, 1.27], [-1.27, 1.27]
    return pins, (min(xs), min(ys), max(xs), max(ys))


# ----------------------------------------------------------------------
# Layout helpers
# ----------------------------------------------------------------------
OUTWARD = {0: 180, 180: 0, 90: 270, 270: 90}     # pin angle -> label direction (screen, CCW)


def snap(v):
    return round(v / GRID) * GRID


def label_len(text):
    return len(text) * CHAR_W + LABEL_PAD


def effects(justify=None, hide=False):
    e = ["effects", ["font", ["size", FONT, FONT]]]
    if justify:
        e.append(["justify", justify])
    if hide:
        e.append(["hide", "yes"])
    return e


def prop(name, value, x, y, justify=None, hide=False, angle=0):
    return ["property", esc(name), esc(value), ["at", x, y, angle], effects(justify, hide)]


class PlacedPart:
    def __init__(self, part, sym):
        self.part = part
        self.sym = sym
        self.pins, (x0, y0, x1, y1) = symbol_geometry(sym)
        self.body = (x0, -y1, x1, -y0)                       # screen coords (y down), relative
        ext = {0: 0.0, 90: 0.0, 180: 0.0, 270: 0.0}
        self.labels = []
        for pin in part.pins:
            if pin.num not in self.pins:
                raise ValueError(f"{part.ref}: pin {pin.num} not found in unit 1 of {part.name}")
            x, y, ang, ptype, hidden = self.pins[pin.num]
            net = pin.net
            is_nc = net is None or type(net).__name__ == "NCNet"
            if hidden:
                if is_nc or ptype == "no_connect":
                    continue
                stacked = [q for q in part.pins if q.num != pin.num and not self.pins[q.num][4]
                           and self.pins[q.num][:2] == (x, y) and q.net is net]
                if ptype != "power_in" and stacked:
                    continue      # hidden pin stacked on a visible pin of the same net
                raise ValueError(f"{part.ref}: hidden pin {pin.num} ({ptype}) carries net {net.name}")
            out = OUTWARD[ang]
            if is_nc:
                self.labels.append((pin.num, x, -y, out, None))
            else:
                self.labels.append((pin.num, x, -y, out, net.name))
                ext[out] = max(ext[out], label_len(net.name))
        text = max(len(part.ref), len(str(part.value))) * CHAR_W
        bx0, by0, bx1, by1 = self.body
        self.left = snap(ext[180] + 2.54)
        self.right = snap(max(ext[0], text + 2.54) + 2.54)
        self.top = snap(max(ext[90], 2 * GRID + 1.27) + 2.54)
        self.bottom = snap(ext[270] + 2.54)
        self.w = self.left + (bx1 - bx0) + self.right
        self.h = self.top + (by1 - by0) + self.bottom
        self.x = self.y = 0.0

    def place(self, cell_x, cell_y):
        bx0, by0, _, _ = self.body
        self.x = snap(cell_x + self.left - bx0)
        self.y = snap(cell_y + self.top - by0)


def pack(items, max_w, gap=2.54):
    """Row packing; returns used width and height."""
    x = y = row_h = used_w = 0.0
    for it in items:
        if x > 0 and x + it.w > max_w:
            x, y, row_h = 0.0, y + row_h + gap, 0.0
        it.place(x, y)
        x += it.w + gap
        row_h = max(row_h, it.h)
        used_w = max(used_w, x)
    return used_w, y + row_h


# ----------------------------------------------------------------------
# Writer
# ----------------------------------------------------------------------
class SheetWriter:
    MARGIN = 25.4

    def __init__(self, project, root_uuid, sheet_uuid, title, page):
        self.project = project
        self.root_uuid = root_uuid
        self.sheet_uuid = sheet_uuid
        self.title = title
        self.page = page
        self.lib_symbols = {}
        self.items = []

    def path(self):
        return f"/{self.root_uuid}" + (f"/{self.sheet_uuid}" if self.sheet_uuid != self.root_uuid else "")

    def symbol(self, lib_id, sym, ref, value, x, y, extra_props, pins, in_bom=None, on_board=None,
               ref_at=None, val_at=None):
        if lib_id not in self.lib_symbols:
            s = copy.deepcopy(sym)
            s[1] = Q(lib_id)
            self.lib_symbols[lib_id] = s
        if in_bom is None:
            in_bom = (child(sym, "in_bom") or ["", "yes"])[1] == "yes"
        if on_board is None:
            on_board = (child(sym, "on_board") or ["", "yes"])[1] == "yes"
        u = uid(self.project, self.path(), ref)
        node = ["symbol", ["lib_id", esc(lib_id)], ["at", x, y, 0], ["unit", 1],
                ["exclude_from_sim", "no"], ["in_bom", "yes" if in_bom else "no"],
                ["on_board", "yes" if on_board else "no"], ["dnp", "no"], ["uuid", u]]
        rx, ry = ref_at or (x, y - 2.54)
        vx, vy = val_at or (x, y + 2.54)
        node.append(prop("Reference", ref, rx, ry, "left"))
        node.append(prop("Value", value, vx, vy, "left"))
        for k, v in extra_props:
            node.append(prop(k, v, x, y, hide=True))
        for num in pins:
            node.append(["pin", esc(num), ["uuid", uid(u, "pin", num)]])
        node.append(["instances", ["project", esc(self.project),
                                   ["path", esc(self.path()), ["reference", esc(ref)], ["unit", 1]]]])
        self.items.append(node)

    def label(self, name, x, y, angle):
        just = "left" if angle in (0, 90) else "right"
        self.items.append(["global_label", esc(name), ["shape", "passive"], ["at", x, y, angle],
                           ["fields_autoplaced", "yes"], effects(just), ["uuid", uid(self.path(), name, f"{x:.2f}", f"{y:.2f}")]])

    def no_connect(self, x, y):
        self.items.append(["no_connect", ["at", x, y], ["uuid", uid(self.path(), "nc", f"{x:.2f}", f"{y:.2f}")]])

    def text(self, s, x, y, size=2.54):
        self.items.append(["text", esc(s), ["exclude_from_sim", "no"], ["at", x, y, 0],
                           ["effects", ["font", ["size", size, size]], ["justify", "left", "top"]],
                           ["uuid", uid(self.path(), "text", s[:40])]])

    def write(self, filename, paper, extra=()):
        tree = ["kicad_sch", ["version", FORMAT_VERSION], ["generator", Q("calu_sch_writer")],
                ["generator_version", Q("1.0")], ["uuid", self.sheet_uuid], ["paper", Q(paper)],
                ["title_block", ["title", esc(self.title)], ["rev", Q("3.0.0.0")],
                 ["comment", 1, Q("Generated from hw/slave_3_0/*.py (SKiDL) - edit the Python source, not this file")]],
                ["lib_symbols"] + list(self.lib_symbols.values())]
        tree += self.items + list(extra)
        with open(filename, "w", encoding="utf-8", newline="\n") as f:
            f.write(dump(tree) + "\n")


def footprint_excluded_from_bom(fp_id):
    if not fp_id or ":" not in fp_id:
        return False
    lib, name = fp_id.split(":")
    root = os.environ.get("KICAD10_FOOTPRINT_DIR", "")
    try:
        with open(os.path.join(root, lib + ".pretty", name + ".kicad_mod"), encoding="utf-8") as f:
            return "exclude_from_bom" in f.read()
    except OSError:
        return False


def place_parts(writer, parts, max_w, origin=None):
    placed = [PlacedPart(p, flat_symbol(p.lib.filename, p.name)) for p in parts]
    used_w, used_h = pack(placed, max_w)
    ox, oy = origin or (writer.MARGIN, writer.MARGIN + 10.16)
    for pp in placed:
        p = pp.part
        x, y = pp.x + ox, pp.y + oy
        bx0, by0, bx1, _ = pp.body
        props = [("Footprint", p.footprint or ""), ("Datasheet", "~")]
        props += [(k, v) for k, v in p.fields.items() if k not in ("Footprint", "Datasheet", "Reference", "Value")]
        writer.symbol(f"{p.lib.filename}:{p.name}", pp.sym, p.ref, p.value, x, y, props,
                      [n for n, *_ in pp.labels],
                      in_bom=False if footprint_excluded_from_bom(p.footprint) else None,
                      ref_at=(x + bx1 + 1.27, y + by0 - 3.81), val_at=(x + bx1 + 1.27, y + by0 - 1.27))
        for num, lx, ly, angle, net in pp.labels:
            if net is None:
                writer.no_connect(x + lx, y + ly)
            else:
                writer.label(net, x + lx, y + ly, angle)
    return used_w + 2 * writer.MARGIN, used_h + 2 * writer.MARGIN + 10


def choose_paper(w, h):
    for name, pw, ph in PAPERS:
        if w <= pw and h <= ph:
            return name
    return PAPERS[-1][0]


def power_flags(writer, x, y):
    """PWR_FLAG on every net with power-input pins but no power output (KiCad ERC)."""
    nets = {}
    for p in builtins.default_circuit.parts:
        pins, _ = symbol_geometry(flat_symbol(p.lib.filename, p.name))
        for pin in p.pins:
            if pin.net is None or type(pin.net).__name__ == "NCNet":
                continue
            nets.setdefault(pin.net.name, set()).add(pins[pin.num][3])
    flag = flat_symbol("power", "PWR_FLAG")
    fpins, _ = symbol_geometry(flag)
    (num, (px, py, ang, *_)), = fpins.items()
    n = 0
    for name in sorted(nets):
        types = nets[name]
        if "power_in" in types and "power_out" not in types:
            n += 1
            fx = x + (n - 1) * 25.4
            writer.symbol("power:PWR_FLAG", flag, f"#FLG{n:02d}", "PWR_FLAG", fx, y, [("Footprint", ""), ("Datasheet", "~")],
                          [num], in_bom=False, on_board=False)
            writer.label(name, fx + px, y - py, OUTWARD[ang])
    return n


def write_schematic(out_dir, project, title, sheet_order, max_w=760.0):
    root_uuid = uid(project, "root")
    by_sheet = {}
    for p in builtins.default_circuit.parts:
        name = p.hiertuple[1] if len(p.hiertuple) > 1 else ""
        by_sheet.setdefault(name, []).append(p)

    sheet_nodes = []
    for i, name in enumerate(sheet_order):
        s_uuid = uid(project, "sheet", name)
        w = SheetWriter(project, root_uuid, s_uuid, f"{title} - {name}", str(i + 2))
        used_w, used_h = place_parts(w, by_sheet.get(name, []), max_w)
        fname = f"{project}_{name}.kicad_sch"
        w.write(os.path.join(out_dir, fname), choose_paper(used_w, used_h))
        x, y = 25.4 + i * 45.72, 50.8
        sheet_nodes.append(
            ["sheet", ["at", x, y], ["size", 38.1, 20.32], ["exclude_from_sim", "no"], ["in_bom", "yes"],
             ["on_board", "yes"], ["dnp", "no"], ["fields_autoplaced", "yes"],
             ["stroke", ["width", 0.1524], ["type", "solid"]], ["fill", ["color", 0, 0, 0, 0.0]], ["uuid", s_uuid],
             prop("Sheetname", name, x, y - 0.7, "left"),
             prop("Sheetfile", fname, x, y + 21.0, "left"),
             ["instances", ["project", esc(project), ["path", esc(f"/{root_uuid}"), ["page", Q(str(i + 2))]]]]])

    root = SheetWriter(project, root_uuid, root_uuid, title, "1")
    root.text("CALU BMS Slave 3.0.0.0 - flying-capacitor cell measurement\n"
              "Source: hw/slave_3_0/*.py (SKiDL), specification: hw/CALU_BMS_Slave_3_0_0_0_schematic.md\n"
              "Connections are made by global labels (net names), every sheet is generated.", 25.4, 20.32)
    place_parts(root, by_sheet.get("", []), 300, origin=(25.4, 88.9))
    power_flags(root, 25.4, 160.02)
    root.write(os.path.join(out_dir, f"{project}.kicad_sch"), "A3",
               extra=sheet_nodes + [["sheet_instances", ["path", Q("/"), ["page", Q("1")]]]])


# ----------------------------------------------------------------------
# Project file and verification
# ----------------------------------------------------------------------
def _netclass(name, clearance, track, priority):
    return {"name": name, "clearance": clearance, "track_width": track, "via_diameter": 0.6, "via_drill": 0.3,
            "microvia_diameter": 0.3, "microvia_drill": 0.1, "diff_pair_width": 0.2, "diff_pair_gap": 0.25,
            "diff_pair_via_gap": 0.25, "wire_width": 6, "bus_width": 12, "line_style": 0,
            "schematic_color": "rgba(0, 0, 0, 0.000)", "pcb_color": "rgba(0, 0, 0, 0.000)", "priority": priority}


def write_project(out_dir, project, netclass_patterns):
    path = os.path.join(out_dir, project + ".kicad_pro")
    data = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    data.setdefault("meta", {"filename": project + ".kicad_pro", "version": 3})
    data["net_settings"] = {
        "classes": [_netclass("Default", 0.2, 0.25, 2147483647),
                    _netclass("HV", 0.6, 0.3, 1),
                    _netclass("BAL", 0.6, 0.6, 0)],
        "meta": {"version": 4},
        "net_colors": None,
        "netclass_assignments": None,
        "netclass_patterns": [{"netclass": c, "pattern": p} for c, p in netclass_patterns],
    }
    # 0.2 mm holes for the thermal vias of the LM5164 and ESP32 footprints (JLCPCB standard capability)
    rules = data.setdefault("board", {}).setdefault("design_settings", {}).setdefault("rules", {})
    rules["min_through_hole_diameter"] = 0.2
    rules["min_hole_to_hole"] = 0.25
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def _netlist_groups(path):
    tree = parse(open(path, encoding="utf-8").read())
    nets = child(tree, "nets")
    groups = {}
    for n in children(nets, "net"):
        name = child(n, "name")[1]
        nodes = frozenset((child(nd, "ref")[1], child(nd, "pin")[1]) for nd in children(n, "node"))
        if len(nodes) > 1 or not name.startswith("unconnected-"):
            groups[name.lstrip("/")] = nodes
    return groups


def verify_schematic(out_dir, project, kicad_cli, skidl_net):
    """Compare KiCad's netlist of the generated schematic with the SKiDL netlist.
    Returns (problems, unconnected) with unconnected = {(ref, pin): KiCad net name} for no-connect pins."""
    sch = os.path.join(out_dir, project + ".kicad_sch")
    exported = os.path.join(out_dir, project + "_from_sch.net")
    subprocess.run([kicad_cli, "sch", "export", "netlist", "--format", "kicadsexpr", "-o", exported, sch],
                   check=True, capture_output=True)
    a = {k: v for k, v in _netlist_groups(skidl_net).items() if len(v) > 1}
    all_b = _netlist_groups(exported)
    b = {k: v for k, v in all_b.items() if len(v) > 1}
    unconnected = {}
    tree = parse(open(exported, encoding="utf-8").read())
    for n in children(child(tree, "nets"), "net"):
        name = child(n, "name")[1]
        if name.startswith("unconnected-"):
            for nd in children(n, "node"):
                unconnected[(child(nd, "ref")[1], child(nd, "pin")[1])] = name
    problems = []
    for name, nodes in a.items():
        if b.get(name) != nodes:
            problems.append(f"net {name}: skidl {sorted(nodes)[:4]}... vs schematic {sorted(b.get(name, []))[:4]}...")
    for name in b.keys() - a.keys():
        problems.append(f"extra net in schematic: {name} {sorted(b[name])[:4]}")
    os.remove(exported)
    return problems, unconnected
