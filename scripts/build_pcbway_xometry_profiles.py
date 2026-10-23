#!/usr/bin/env python3
"""Build manufacturers/pcbway.json and xometry.json (schema v2) from the owner-supplied research snapshot.

Inputs (saved verbatim in manufacturers/sources/): pcbway_buildability_rules_v1_2026-10-23.json,
xometry_buildability_rules_v1_2026-10-23.json. Every threshold is read from those files (never retyped) and
every source rule id used here must exist. All rules are provisional and non-blocking: the data is second-hand
(compiled by an external research session, not re-fetched by this project), so it can raise warnings / review items
and support a "conditionally compatible" verdict, but can never establish "compatible" or fail a part.
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "manufacturers", "sources")
IN = 25.4
D = "2026-10-23"
PROV = ("Owner-supplied research snapshot 2026-10-23 ({file}); compiled by an external research session from the cited public page, "
        "not re-fetched by this project. Treat as provisional until re-checked against the page.")


def load(name):
    d = json.load(open(os.path.join(SRC, name)))
    return d, {r["id"]: r for r in d["rules"]}


class Builder:
    def __init__(self, mfr, file, rules_by_id):
        self.mfr, self.file, self.by = mfr, file, rules_by_id

    def src(self, *ids, note=""):
        for i in ids:
            assert i in self.by, f"unknown source rule {i}"
        urls = {self.by[i]["source_url"] for i in ids}
        assert len(urls) == 1, f"mixed urls for {ids}"
        return {"url": urls.pop(), "date_verified": D, "snapshot": True, "provenance": PROV.format(file=self.file),
                "source_rule_ids": list(ids), "note": note or "; ".join(self.by[i]["notes"] for i in ids)}

    def th(self, i):
        return self.by[i]["threshold"]

    def rule(self, rid, rtype, params, ids, consequence, notes, severity="WARNING", applies_to=None, **extra):
        r = {"id": rid, "type": rtype, "enabled": True, "verified": True, "provisional": True, "severity": severity,
             "consequence": consequence, "parameters": params, "notes": notes, "source": self.src(*ids)}
        if applies_to:
            r["applies_to"] = applies_to
        r.update(extra)
        return r

    def off(self, rid, rtype, ids, why):
        return {"id": rid, "type": rtype, "enabled": False, "verified": False, "severity": "WARNING", "parameters": {},
                "limitations": why, "source": self.src(*ids)}

    def restriction(self, rid, text, *ids):
        return {"id": rid, "text": text, "modelled": False, "source": self.src(*ids)}


def xometry():
    d, by = load("xometry_buildability_rules_v1_2026-10-23.json")
    b = Builder("xometry", "xometry_buildability_rules_v1.json", by)
    th = b.th
    assert by["XOM-SM-001"]["unit"] == "times_material_thickness" and by["XOM-CAP-003"]["unit"] == "in"
    sheet_rules = [
        b.rule("xom.thickness_typical", "thickness_range", {"min_mm": round(th("XOM-CAP-001") * IN, 4), "max_mm": round(th("XOM-CAP-002") * IN, 4)},
               ["XOM-CAP-001", "XOM-CAP-002"], "review", "Typical range only; thinner/thicker sheet is available by review, so an out-of-range value needs confirmation, not rejection.", "WARNING"),
        b.rule("xom.max_blank", "max_part_dimensions", {"max_long_mm": round(th("XOM-CAP-004") * IN, 2), "max_short_mm": round(th("XOM-CAP-003") * IN, 2)},
               ["XOM-CAP-003", "XOM-CAP-004"], "review", "Nominal 5 x 10 ft blank; larger on request. Compared with the flat-pattern bounding box."),
        b.rule("xom.min_bend_radius", "min_bend_radius", {"min_ratio_to_thickness": th("XOM-SM-001")}, ["XOM-SM-001"], "warning",
               "Published as minimum bend 1x material thickness; treated as an inside-radius recommendation. Material and tooling may require more."),
        b.rule("xom.hole_edge", "min_hole_edge_distance", {"min_ratio_to_thickness": th("XOM-SM-002")}, ["XOM-SM-002"], "warning",
               "Published as hole-edge to part-edge, edge-to-edge (matches how the add-in measures)."),
        b.off("xom.bend_to_hole", "min_hole_bend_distance", ["XOM-SM-004"], "6x thickness published; the bend-edge datum is ambiguous (tangent line vs bend line), so it is not automated."),
    ]
    sheet_restr = [("XOM-SM-003", "Hole-to-hole spacing 6x thickness: the publisher does not say center-to-center or edge-to-edge and notes it should not be automated until resolved; hole-to-hole spacing is also not extracted."),
                   ("XOM-SM-005", "Feature-to-countersink 8x thickness: feature datum ambiguous; countersinks are not extracted."),
                   ("XOM-SM-006", "Minimum countersink depth 0.6x thickness (check suitability for thickness and screw design); countersinks are not extracted."),
                   ("XOM-SM-007", "Relief cuts 1x thickness: relief width vs depth unclear; reliefs are not extracted."),
                   ("XOM-SM-008", "Corner fillet radius 0.5x thickness: fillet geometry unclear; not extracted.")]
    cnc = [("XOM-CNC-001", "Minimum metal wall 0.794 mm (design recommendation)"), ("XOM-CNC-002", "Minimum plastic wall 1.5 mm"),
           ("XOM-CNC-003", "Cavity depth:width ratio <= 5 (3-5 recommended)"), ("XOM-CNC-004", "Internal corner radius >= 1.3x tool radius (rule of thumb)"),
           ("XOM-CNC-005", "Thread depth <= 2x diameter (typically 1.5-2x; cost guidance)"), ("XOM-CNC-006", "Blind hole: unthreaded bottom >= 0.5x diameter"),
           ("XOM-CNC-007", "Feature size >= 2.5 mm (common tool size; smaller with special tools)"), ("XOM-CNC-008", "Drilled hole depth <= 4x diameter (up to 10x possible but costly)")]
    for i, t in cnc:   # sanity: the transcribed text must agree with the source numbers
        assert str(by[i]["threshold"]).rstrip("0").rstrip(".") in t or str(by[i]["threshold"]) in t, (i, by[i]["threshold"])
    return {
        "schema_version": 2, "manufacturer": {"id": "xometry", "name": "Xometry", "website": "https://www.xometry.com"},
        "profile_status": "partially_verified",
        "description": "Published Xometry sheet-metal capabilities and design tips from an owner-supplied research snapshot (2026-10-23). Second-hand and provisional: every rule is non-blocking and can never produce a 'compatible' verdict.",
        "research": {"status": "partial", "attempted": D,
                     "notes": "Data supplied by the project owner from an external research session; this project's build environment could not reach xometry.com. Full downloadable design guides were not extracted. Ambiguous datums (hole-to-hole, bend-edge-to-hole, countersink, relief) are left disabled. Supplier/process-specific capability needs quote confirmation. Electrical suitability and certification are not assessed."},
        "processes": [
            {"id": "sheet_metal_bending", "name": "Sheet metal fabrication (published capabilities)", "thickness_match_tolerance_mm": 0.05,
             "materials": [], "restrictions": [b.restriction(f"xom.r.{i.split('XOM-')[1].lower()}", t, i) for i, t in sheet_restr], "notes": ["Rules are expressed as multiples of material thickness, so they apply to any material."],
             "tolerances": [{"id": "xom.tol.quoted", "text": "Automatic quoting tolerance as tight as +/-0.005 in for some dimensions; tighter requires manual review", "value": round(th("XOM-CAP-005") * IN, 4), "units": "mm",
                             "source": b.src("XOM-CAP-005")}],
             "rules": sheet_rules},
            {"id": "cnc_machining", "name": "CNC machining (design tips; not evaluated)", "materials": [], "rules": [], "tolerances": [],
             "notes": ["CNC tips are recorded as restrictions only; machining is outside the current sheet-metal scope."],
             "restrictions": [b.restriction(f"xom.cnc.{i.split('-')[-1]}", t, i) for i, t in cnc]}]}


def pcbway():
    d, by = load("pcbway_buildability_rules_v1_2026-10-23.json")
    b = Builder("pcbway", "pcbway_buildability_rules_v1.json", by)
    th = b.th
    fam = {"steel": ("Steel (carbon/mild)", ["steel", "carbon steel", "mild steel"], "PCB-SHEET-STEEL"),
           "stainless_steel": ("Stainless steel", ["stainless"], "PCB-SHEET-STAINLESS_STEEL"),
           "aluminum": ("Aluminum", ["aluminum", "aluminium"], "PCB-SHEET-ALUMINUM"),
           "titanium": ("Titanium", ["titanium"], "PCB-SHEET-TITANIUM"),
           "copper": ("Copper", ["copper"], "PCB-SHEET-COPPER")}
    margin = th("PCB-STOCK-EDGE")
    assert margin == 5
    rules = [
        b.rule("pcb.min_part", "min_part_dimensions", {"min_long_mm": th("PCB-BEND-001"), "min_short_mm": th("PCB-BEND-001")}, ["PCB-BEND-001"], "review",
               "Minimum finished part 3 x 3 mm. Compared with the flat-pattern size (a proxy for the finished part)."),
        b.rule("pcb.min_flange", "min_flange_length", {"min_ratio_to_thickness": 4.0, "measure": "tangent"}, ["PCB-BEND-002"], "warning",
               "Standard minimum bend height 4x thickness (smaller possible under special conditions). The datum is not published; the add-in measures from the bend tangent line, which is conservative. A separate PCBWay article states inside radius + 4T, which is stricter; both are preserved (see pcb.min_flange_radius_plus_4t) and not silently reconciled."),
        b.rule("pcb.feature_to_bend", "min_hole_bend_distance", {"min_ratio_to_thickness": 2.0, "measure": "centerline"}, ["PCB-BEND-004"], "warning",
               "Initial clearance guideline of 2x thickness from the hole/cutout edge to the bend line; larger clearance may be needed. Measured to the bend centerline (tangent distance plus half the bend zone)."),
        b.off("pcb.min_flange_radius_plus_4t", "min_flange_length", ["PCB-BEND-002"], "A separate PCBWay article states minimum flange = inside bend radius + 4T. It conflicts with the 4T guidance and its datum is unclear, so it is recorded but not evaluated."),
        b.off("pcb.min_bend_radius", "min_bend_radius", ["PCB-BEND-003"], "PCBWay states the minimum radius depends on material grade, temper, thickness, grain direction and tooling; do not apply a universal R >= T."),
    ]
    for key, (name, _, sid) in fam.items():
        long_, short = sorted(th(sid), reverse=True)
        rules.append(b.rule(f"pcb.stock.{key}", "max_part_dimensions", {"max_long_mm": long_ - 2 * margin, "max_short_mm": short - 2 * margin}, [sid, "PCB-STOCK-EDGE"], "review",
                            f"Published raw-stock maximum {long_} x {short} mm minus a {margin} mm cutting margin on each side (= {long_ - 2 * margin} x {short - 2 * margin} mm); a flat pattern may be rotated 90 degrees. This is a raw-stock limit, not a finished-part guarantee.",
                            applies_to={"materials": [key]}))
    cut_src = "https://www.pcbway.com/blog/Sheet-Cutting/Sheet_Cutting_Design_Guidelines_b0e8981b.html"
    routing = [
        b.rule("pcb.route.min_part", "min_part_dimensions", {"min_long_mm": th("PCB-CUT-005"), "min_short_mm": th("PCB-CUT-005")}, ["PCB-CUT-005"], "review",
               "General CNC-routing minimum part dimension; specific materials vary."),
        b.rule("pcb.route.max_part", "max_part_dimensions", {"max_long_mm": th("PCB-CUT-006"), "max_short_mm": th("PCB-CUT-006")}, ["PCB-CUT-006"], "review",
               "General CNC-routing upper dimension; engineer review may differ."),
        b.rule("pcb.route.min_hole", "min_hole_diameter", {"min_mm": th("PCB-CUT-007")}, ["PCB-CUT-007"], "review",
               "General CNC-routing minimum diameter; process-specific."),
    ]
    route_restr = [("PCB-CUT-008", "Routed internal corners cannot be sharp: radius >= 0.063 in (depends on bit size)"),
                   ("PCB-CUT-009", "Dogbone relief diameter >= tool bit diameter + 0.005 in for square mating pockets"),
                   ("PCB-CUT-010", "Perforated/skeletal flatbed parts: removed area <= 50%"),
                   ("PCB-CUT-011", "Holding-tab placement needs >= 0.4 in between edge vertices")]
    sheet_restr = [("PCB-BEND-006", "Bend angles below 5 degrees or included angles above 130 degrees need manual review (special/near-flat bends, tooling access); no numeric rule is published."),
                   ("PCB-FORM-001", "0.187 and 0.250 in sheet: both flanges need full bend-length support; support coverage is not extracted."),
                   ("PCB-CUT-001", "Formed-sheet STEP submissions must contain a single solid body."),
                   ("PCB-CUT-004", "3D assemblies / pre-nested parts must be uploaded as individual parts."),
                   ("PCB-CUT-002", "2D cutting profiles must be closed outlines."), ("PCB-CUT-003", "No duplicate/overlapping cut lines in 2D files."),
                   ("PCB-HW-001", "Hardware: hole center to edge >= 1.5x mounting-hole diameter (rule of thumb; use hardware datasheet)."),
                   ("PCB-HW-002", "Hardware: hole center to edge >= 2x diameter for high-load/thin sheet (advisory)."),
                   ("PCB-HW-003", "Hardware: adjacent same-hardware center spacing >= 3x diameter."),
                   ("PCB-HW-004", "Hardware: center to bend tangent >= inside radius + thickness + hardware margin."),
                   ("PCB-HW-005", "Hardware: center to bend line >= 2x thickness + inside radius + 3 mm (advisory)."),
                   ("PCB-HW-006", "Hardware compatibility (fastener vs sheet hardness, vendor datasheet) needs manual review.")]
    return {
        "schema_version": 2, "manufacturer": {"id": "pcbway", "name": "PCBWay", "website": "https://www.pcbway.com"},
        "profile_status": "partially_verified",
        "description": "Published PCBWay sheet-metal/flatbed-cutting/hardware guidelines from an owner-supplied research snapshot (2026-10-23). Second-hand and provisional (the snapshot itself says entries need checking against the primary pages): every rule is non-blocking and can never produce a 'compatible' verdict.",
        "research": {"status": "partial", "attempted": D,
                     "notes": "Data supplied by the project owner from an external research session; this project's build environment could not reach pcbway.com. Not a comprehensive or certified capabilities database; not PCBWay-approved. Unresolved: minimum hole size by material/process, thickness catalog by alloy, CNC tolerance tables, countersink/counterbore rules, tapping engagement, bend radius per alloy/temper, PEM catalog dimensions, bend-line vs bend-tangent datum, laser kerf per material."},
        "processes": [
            {"id": "sheet_metal_bending", "name": "Sheet metal bending (published guidelines)", "thickness_match_tolerance_mm": 0.05,
             "materials": [{"id": k, "name": v[0], "aliases": v[1]} for k, v in fam.items()],
             "tolerances": [],
             "restrictions": [b.restriction(f"pcb.r.{i.split('PCB-')[1].lower()}", t, i) for i, t in sheet_restr],
             "notes": ["Bend allowance (info only): BA = pi * (inside_radius + k * thickness) * angle / 180.",
                       "Steel/aluminum/titanium/copper stock limits are raw sheet sizes, not maximum finished part sizes."],
             "rules": rules},
            {"id": "cnc_routing", "name": "Flatbed / CNC routing (published guidelines)", "thickness_match_tolerance_mm": 0.05, "materials": [], "tolerances": [],
             "restrictions": [b.restriction(f"pcb.r.{i.split('PCB-')[1].lower()}", t, i) for i, t in route_restr],
             "notes": ["Applicability of routing limits to metal sheet is not stated by the source; verify before relying on them."],
             "rules": routing}]}


if __name__ == "__main__":
    for name, fn in (("xometry", xometry), ("pcbway", pcbway)):
        out = os.path.join(ROOT, "manufacturers", name + ".json")
        json.dump(fn(), open(out, "w"), indent=1)
        print("wrote", out)
