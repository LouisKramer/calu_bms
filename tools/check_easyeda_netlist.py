"""Compare an EasyEDA Pro project (.epro2) with a reference netlist CSV (hw/<board>/*_netlist.csv).

Usage:
    python tools/check_easyeda_netlist.py hw/slave/slave_4_0.epro2 hw/slave/slave_4_0_netlist.csv [-o report.md]

The pad nets are read from the PCB document of the project (run "Update PCB from schematic" in EasyEDA first).
Parts are matched by designator; parts that were renamed are found by their connections. Nets are matched by
name where the names agree, otherwise by the parts connected to them (auto-named nets like $2N138).
For two-terminal parts without polarity (pin names 1/2 in the reference) the pin order does not matter.
"""

import argparse
import collections
import csv
import json
import re
import sys
import zipfile


# ---- EasyEDA project -------------------------------------------------------------------------------------------

def read_records(path):
    z = zipfile.ZipFile(path)
    name = next(n for n in z.namelist() if n.endswith(".epru"))
    docs, cur = [], None
    for line in z.read(name).decode("utf-8").splitlines():
        head, _, rest = line.partition("||")
        try:
            hj = json.loads(head)
            body = json.loads(rest.rstrip("|")) if rest.strip("|") else {}
        except ValueError:
            continue
        if hj.get("type") == "DOCHEAD":
            cur = {"type": body.get("docType"), "uuid": body.get("uuid"), "title": None, "meta": {}, "records": []}
            docs.append(cur)
        elif cur is not None:
            if hj.get("type") == "META" and cur["title"] is None:
                cur["title"] = body.get("title")
                cur["meta"] = body.get("attributes") or {}
            cur["records"].append((hj, body))
    return docs


def symbol_pins(docs):
    """Symbol uuid -> {pin number: pin name}."""
    out = {}
    for d in docs:
        if d["type"] != "SYMBOL":
            continue
        pins, attrs = [], collections.defaultdict(dict)
        for hj, body in d["records"]:
            if hj.get("type") == "PIN":
                pins.append(hj["id"])
            elif hj.get("type") == "ATTR" and body.get("parentId"):
                attrs[body["parentId"]][body.get("key")] = body.get("value")
        out[d["uuid"]] = {str(attrs[p].get("Pin Number")): attrs[p].get("Pin Name") or "" for p in pins}
    return out


def easyeda_parts(docs):
    pcbs = [d for d in docs if d["type"] == "PCB"]
    if not pcbs:
        sys.exit("no PCB document in the project: run 'Update PCB from schematic' in EasyEDA first")
    pcb = max(pcbs, key=lambda d: sum(1 for hj, _ in d["records"] if hj.get("type") == "PAD_NET"))
    devices = {d["uuid"]: d for d in docs if d["type"] == "DEVICE"}
    symbols = symbol_pins(docs)
    attrs, pads = collections.defaultdict(dict), collections.defaultdict(dict)
    for hj, body in pcb["records"]:
        t = hj.get("type")
        if t == "COMPONENT":
            attrs[hj["id"]].update(body.get("attrs") or {})
        elif t == "ATTR" and body.get("parentId"):
            attrs[body["parentId"]][body.get("key")] = body.get("value")
        elif t == "PAD_NET":
            _, cid, pad, _ = json.loads(hj["id"])
            pads[cid][str(pad)] = body.get("padNet") or ""
    parts = {}
    for cid, a in attrs.items():
        des = a.get("Designator")
        if not des or cid not in pads:
            continue
        dev = devices.get(a.get("Device"), {})
        meta = dev.get("meta", {})
        parts[des] = {"device": dev.get("title") or a.get("Device") or "", "value": a.get("Value") or meta.get("Value") or "",
                      "lcsc": meta.get("Supplier Part") or a.get("Supplier Part") or "",
                      "mpn": meta.get("Manufacturer Part") or a.get("Manufacturer Part") or "", "pads": pads[cid],
                      "names": symbols.get(meta.get("Symbol"), {})}
    return parts


# ---- reference -------------------------------------------------------------------------------------------------

def reference_parts(path):
    parts = {}
    for r in csv.DictReader(open(path, encoding="utf-8")):
        p = parts.setdefault(r["ref"], {"page": r["page"], "value": r["value"], "part": r["part"], "lcsc": r["lcsc"],
                                        "pins": {}, "names": {}})
        p["pins"][r["pin"]] = "" if r["net"] == "nc" else r["net"]
        p["names"][r["pin"]] = r["pin_name"]
    return parts


def symmetric(p):
    return len(p["pins"]) == 2 and set(p["names"].values()) == {"1", "2"}


def polarized(p):
    return len(p["pins"]) == 2 and not symmetric(p)


POSITIVE = {"A", "ANODE", "+", "P"}
NEGATIVE = {"K", "C", "CATHODE", "-", "−", "N"}


def polarity(name):
    n = (name or "").strip().upper()
    return "+" if n in POSITIVE else "-" if n in NEGATIVE else None


def norm_pin_name(name):
    n = (name or "").upper().replace("D+", "DP").replace("D−", "DN").replace("D-", "DN")
    n = {"SH": "SHELL", "SHIELD": "SHELL"}.get(n, n)
    return re.sub(r"^(DP|DN|SHELL)\d+$", r"\1", n)


def pad_map(p, e):
    """Reference pin -> EasyEDA pad, or None when the parts must be compared by pin name."""
    if polarized(p) and all(polarity(n) for n in e["names"].values()) and len(e["names"]) == 2:
        by_pol = {polarity(n): pad for pad, n in e["names"].items()}
        return {pin: by_pol.get(polarity(name)) for pin, name in p["names"].items()}
    if len(set(p["pins"]) & set(e["pads"])) * 2 >= len(p["pins"]):
        return {pin: pin for pin in p["pins"]}
    return None


# ---- comparison ------------------------------------------------------------------------------------------------

def map_nets(ref, eda, alias):
    """Reference net -> EasyEDA net, by name and by connected pins."""
    eda_nets = {n for p in eda.values() for n in p["pads"].values() if n}
    mapping = {n: n for p in ref.values() for n in p["pins"].values() if n in eda_nets}
    votes = collections.defaultdict(collections.Counter)
    for r, p in ref.items():
        e = eda.get(alias.get(r, r))
        if e is None or symmetric(p):
            continue
        pm = pad_map(p, e)
        if pm is None:
            continue
        for pin, net in p["pins"].items():
            if net and pm[pin] and e["pads"].get(pm[pin]):
                votes[net][e["pads"][pm[pin]]] += 1
    for net, c in votes.items():
        mapping.setdefault(net, c.most_common(1)[0][0])
    changed = True
    while changed:  # chains of resistors/capacitors with unnamed nets
        changed = False
        for r, p in ref.items():
            e = eda.get(alias.get(r, r))
            if e is None or not symmetric(p):
                continue
            a, b = p["pins"]["1"], p["pins"]["2"]
            ea = {n for n in e["pads"].values() if n}
            for known, other in ((a, b), (b, a)):
                if known in mapping and other and other not in mapping and mapping[known] in ea:
                    rest = ea - {mapping[known]}
                    if len(rest) == 1:
                        mapping[other] = rest.pop()
                        changed = True
    return mapping


def mapped_signature(p, mapping):
    return sorted(mapping.get(n, "?" + n) for n in p["pins"].values() if n)


def find_aliases(ref, eda):
    missing = [r for r in ref if r not in eda]
    extra = [e for e in eda if e not in ref]
    alias = {}
    mapping = map_nets(ref, eda, {})
    for r in missing:
        sig = mapped_signature(ref[r], mapping)
        for e in extra:
            if e not in alias.values() and len(eda[e]["pads"]) == len(ref[r]["pins"]) and \
                    sorted(n for n in eda[e]["pads"].values() if n) == sig:
                alias[r] = e
                break
    return alias


def compare_part(r, p, e, mapping, issues):
    got = e["pads"]
    m = lambda n: mapping.get(n, "?" + n) if n else ""
    if symmetric(p):
        want = sorted(m(n) for n in p["pins"].values())
        have = sorted(got.get(k, "") for k in ("1", "2"))
        if len(got) > 2:  # e.g. 4-pad push button: pads are connected in pairs inside
            want, have = sorted(set(want)), sorted(set(n for n in got.values() if n))
        if want != have:
            issues["Wrong connections"].append(f"{r}: expected {fmt_nets(p['pins'].values())}, drawn {fmt_nets(have)}")
        return
    pm = pad_map(p, e)
    if pm is None:  # different pad numbering (e.g. USB-C): compare the nets per pin name
        want, have = collections.defaultdict(set), collections.defaultdict(set)
        for pin, net in p["pins"].items():
            want[norm_pin_name(p["names"][pin])].add(m(net))
        for pad, net in got.items():
            have[norm_pin_name(e["names"].get(pad, pad))].add(net)
        wrong = [f"{name}: expected {fmt_nets(sorted(want[name]))}, drawn {fmt_nets(sorted(have.get(name, {'<missing>'})))}"
                 for name in sorted(want) if want[name] != have.get(name)]
        if wrong:
            issues["Wrong connections"].append(f"{r} (compared by pin name): " + "; ".join(wrong))
        return
    wrong = []
    extra_pads = {got[x] for x in got if x not in p["pins"]}  # e.g. shell pads numbered differently
    for pin, net in sorted(p["pins"].items(), key=lambda x: natural(x[0])):
        pad = pm[pin]
        drawn = got.get(pad, "<no pad>") if pad else "<no pin with this polarity>"
        if drawn == "<no pad>" and m(net) in extra_pads:
            continue
        if drawn != m(net):
            wrong.append((pin, p["names"][pin], net or "nc", drawn or "nc"))
    if not wrong:
        return
    if polarized(p) and sorted(got.values()) == sorted(m(n) for n in p["pins"].values()):
        issues["Reversed"].append(f"{r}: " + ", ".join(f"{name} should be on {net}, drawn on {d}" for _, name, net, d in wrong))
    else:
        issues["Wrong connections"].append(
            f"{r}: " + "; ".join(f"pin {pin} ({name}) expected {net}, drawn {d}" for pin, name, net, d in wrong))


def compare(ref, eda):
    alias = find_aliases(ref, eda)
    mapping = map_nets(ref, eda, alias)
    issues = collections.defaultdict(list)
    for r in sorted(ref, key=natural):
        p = ref[r]
        e = eda.get(alias.get(r, r))
        if e is None:
            issues["Missing parts"].append(f"{r} ({p['value']}, page {p['page']})")
            continue
        compare_part(r, p, e, mapping, issues)
    for r, e in sorted(alias.items(), key=lambda x: natural(x[0])):
        issues["Renamed parts (connections match)"].append(f"{e} should be {r}")
    used = set(alias.values())
    for e in sorted(set(eda) - set(ref) - used, key=natural):
        p = eda[e]
        conns = ", ".join(f"{k}={v or 'nc'}" for k, v in sorted(p["pads"].items(), key=lambda x: natural(x[0])))
        issues["Extra parts (not in the reference)"].append(f"{e} {p['device']} {p['value']}: {conns}")
    inverse = collections.defaultdict(list)
    for rn, en in mapping.items():
        inverse[en].append(rn)
    for en, rns in sorted(inverse.items()):
        if len(rns) > 1:
            issues["Merged nets (short between reference nets)"].append(f"{en} joins {', '.join(sorted(rns))}")
    count = collections.Counter(n for p in eda.values() for n in p["pads"].values() if n)
    for n, c in sorted(count.items()):
        if c == 1 and not any(n == net for p in ref.values() if len(p["pins"]) == 1 for net in p["pins"].values()):
            owner = next(f"{d}.{k}" for d, p in eda.items() for k, v in p["pads"].items() if v == n)
            issues["Nets with only one pin (open)"].append(f"{n} at {owner}")
    for r in sorted(ref, key=natural):
        p, e = ref[r], eda.get(alias.get(r, r))
        if e and p["lcsc"] and e["lcsc"] and p["lcsc"] != e["lcsc"]:
            issues["Different LCSC part"].append(f"{r}: reference {p['lcsc']} ({p['part']}), drawn {e['lcsc']} ({e['mpn'] or e['device']})")
        elif e and not p["lcsc"] and e["value"] and norm_value(e["value"]) != norm_value(p["value"]):
            issues["Different value"].append(f"{r}: reference {p['value']}, drawn {e['value']}")
    return issues, mapping, alias


def natural(s):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s)]


def fmt_nets(nets):
    return " – ".join(n or "nc" for n in nets)


def norm_value(v):
    v = v.replace("µ", "u").replace("Ω", "").replace("\u2126", "").replace("ohm", "").replace(" ", "").lower()
    v = v.split(",")[0]
    v = re.sub(r"^(\d+)([rkm])(\d+)$", r"\1.\3\2", v)  # 4k7 -> 4.7k, 0r1 -> 0.1r
    v = re.sub(r"^(\d+(?:\.\d+)?)r$", r"\1", v)  # 0R -> 0
    return re.sub(r"^(\d+)\.?0*([a-z]*)$", r"\1\2", v)


def report(issues, ref, eda, alias):
    lines = [f"Reference parts: {len(ref)}, EasyEDA parts with pads: {len(eda)}, renamed: {len(alias)}", ""]
    if not issues:
        lines.append("No differences.")
    for title, items in issues.items():
        lines.append(f"## {title} ({len(items)})")
        lines.append("")
        lines += [f"- {i}" for i in items]
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("reference")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()
    eda = easyeda_parts(read_records(args.project))
    ref = reference_parts(args.reference)
    issues, _, alias = compare(ref, eda)
    text = report(issues, ref, eda, alias)
    if args.output:
        open(args.output, "w", encoding="utf-8").write(text + "\n")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
