#!/usr/bin/env python3
"""Parse SendCutSend's published bending tables from saved page HTML into JSON.

Usage: extract_scs_tables.py <bending-calculator.html> <processing-min-max.html> <out.json>
Pages: https://sendcutsend.com/bending-calculator/  and  https://sendcutsend.com/materials/processing-min-max/
Only numbers present in the page text are emitted; anything unparsable raises (no guessing).
"""
import html
import json
import re
import sys


def page_text(path):
    t = open(path, encoding="utf-8", errors="ignore").read()
    t = re.sub(r"<(script|style|nav|header|footer)[^>]*>.*?</\1>", "", t, flags=re.S)
    t = re.sub(r"</(tr|p|li|h\d|div)>", "\n", t)
    t = re.sub(r"</t[dh]>", " | ", t)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return re.sub(r"[ \t]+", " ", t)


def num(s):
    s = s.replace("″", "").replace('"', "").strip()
    if s.upper() in ("N/A", ""):
        return None
    return float(s)


def size(s):
    s = s.replace("″", "").strip()
    if s.upper() == "N/A":
        return None
    a, b = [float(x) for x in s.split("x")]
    return [a, b]


def parse_spec_table(text):
    """Bending specifications per material (bending-calculator page)."""
    i = text.index("Bending specifications per material")
    j = text.index("Additional resources", i)
    flat = re.sub(r"\s*\|\s*\n\s*", "|", text[i:j])
    flat = flat.replace("\n", "")
    header = "Material|Thickness|K Factor|Bend Deduction @ 90°|Effective Bend Radius @ 90°|Die Width|Min Formed Flange Length @ 90°|Min Corner Relief Distance from Bend Line|Bend Relief Depth|"
    out = {}
    for block in flat.split(header)[1:]:
        cells = [c.strip() for c in block.split("|") if c.strip()]
        name, rest = cells[0], cells[1:]
        if len(rest) % 8:
            raise ValueError(f"{name}: {len(rest)} cells is not a multiple of 8")
        rows = []
        for k in range(0, len(rest), 8):
            th, kf, bd, r, die, fl, rel, dep = rest[k:k + 8]
            rows.append({"thickness_in": num(th), "k_factor": num(kf), "bend_deduction_in": num(bd),
                         "bend_radius_in": num(r), "die_width_in": num(die), "min_flange_in": num(fl),
                         "min_corner_relief_in": num(rel), "bend_relief_depth_in": num(dep)})
        out[name] = rows
    return out


def parse_minmax_bending(text):
    """'Min/max part sizes for bending' table (processing-min-max page)."""
    i = text.index("Min/max part sizes for bending")
    j = text.index("Min/max part and countersink sizes", i)
    seg = text[i:j].split("\n")
    out, cur = {}, None
    for line in seg:
        cells = [c.strip() for c in line.split("|") if c.strip()]
        if len(cells) == 8:          # material + 7 columns
            cur = cells[0]; cells = cells[1:]
        elif len(cells) != 7:
            continue
        th, mn, mx, r, bl, fb, fa = cells
        if not re.match(r"^\.\d+", th):
            continue
        out.setdefault(cur, []).append({"thickness_in": num(th), "min_flat_in": size(mn), "max_flat_in": size(mx),
                                        "bend_radius_in": num(r), "max_bend_length_in": num(bl),
                                        "min_flange_flat_pattern_in": num(fb), "min_flange_after_bend_in": num(fa)})
    return out


if __name__ == "__main__":
    spec = parse_spec_table(page_text(sys.argv[1]))
    mm = parse_minmax_bending(page_text(sys.argv[2]))
    json.dump({"spec_table": spec, "minmax_table": mm}, open(sys.argv[3], "w"), indent=1)
    print({k: len(v) for k, v in spec.items()})
    print({k: len(v) for k, v in mm.items()})
