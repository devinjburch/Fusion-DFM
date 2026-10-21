#!/usr/bin/env python3
"""Build manufacturers/sendcutsend.json (schema v2) from the extracted SendCutSend tables.

Inputs: manufacturers/sources/sendcutsend_bending_tables_2026-10-20.json (see extract_scs_tables.py)
        and the Phase 1 hand-entered thickness-range rules (tests/fixtures/phase1_sendcutsend.json).
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN = 25.4
D = "2026-10-20"
U_CALC = "https://sendcutsend.com/bending-calculator/"
U_MINMAX = "https://sendcutsend.com/materials/processing-min-max/"
U_BEND = "https://sendcutsend.com/guidelines/bending/"
U_DEFORM = "https://sendcutsend.com/guidelines/bend-deformation/"
U_CUT = "https://sendcutsend.com/guidelines/sheet-cutting/"
U_MILD = "https://sendcutsend.com/materials/mild-steel/"
MATS = [  # (table name, id, display name, aliases)
    ("5052 Aluminum", "aluminum_5052_h32", "5052 H32 Aluminum", ["5052", "aluminum 5052", "aluminium 5052"]),
    ("Brass", "brass", "Brass", ["brass"]),
    ("4130 Chromoly", "chromoly_4130", "4130 Chromoly", ["4130", "chromoly"]),
    ("Copper", "copper", "Copper", ["copper"]),
    ("G90 Steel", "galvanized_g90", "G90 Galvanized Steel", ["g90", "galvanized"]),
    ("Mild Steel", "mild_steel", "Mild Steel", ["mild steel", "cold rolled", "low carbon"]),
    ("304 Stainless Steel", "stainless_304", "304 Stainless Steel", ["304"]),
    ("316 Stainless Steel", "stainless_316", "316 Stainless Steel", ["316"]),
    ("Titanium Grade 2", "titanium_grade2", "Grade 2 Titanium", ["titanium"]),
]


def mm(v):
    return None if v is None else round(v * IN, 4)


def build_rows(spec_rows, mm_rows):
    rows = []
    for s, m in zip(spec_rows, mm_rows):
        assert s["thickness_in"] == m["thickness_in"] or s["thickness_in"] is not None
        src = {"url": U_CALC, "also": [U_MINMAX], "date_verified": D}
        row = {"thickness_mm": mm(m["thickness_in"]), "thickness_source": f'{m["thickness_in"]:.3f} in',
               "bendable": s["bend_radius_in"] is not None, "source": src, "values": {}}
        if not row["bendable"]:
            row["note"] = "Listed as N/A (not bendable) in both published bending tables."
            rows.append(row)
            continue
        v = row["values"]
        v["k_factor"] = s["k_factor"]
        v["bend_deduction_mm"] = mm(s["bend_deduction_in"])
        v["bend_radius_mm"] = mm(s["bend_radius_in"])
        v["die_width_mm"] = mm(s["die_width_in"])
        v["min_flange_length_mm"] = mm(s["min_flange_in"])
        v["min_corner_relief_mm"] = mm(s["min_corner_relief_in"])
        v["bend_relief_depth_mm"] = mm(s["bend_relief_depth_in"])
        v["min_flange_flat_pattern_mm"] = mm(m["min_flange_flat_pattern_in"])
        v["max_bend_length_mm"] = mm(m["max_bend_length_in"])
        v["min_flat_size_mm"] = [mm(x) for x in m["min_flat_in"]]
        v["max_flat_size_mm"] = [mm(x) for x in m["max_flat_in"]]
        if s["min_flange_in"] != m["min_flange_after_bend_in"]:
            raise SystemExit("flange mismatch")
        if s["bend_radius_in"] != m["bend_radius_in"]:
            row["conflicts"] = {"bend_radius_mm": [
                {"value": mm(s["bend_radius_in"]), "source": {"url": U_CALC, "date_verified": D,
                                                               "note": "Bending specifications per material table"}},
                {"value": mm(m["bend_radius_in"]), "source": {"url": U_MINMAX, "date_verified": D,
                                                               "note": "Min/max part sizes for bending table"}}]}
            row["note"] = ("SendCutSend's two published tables disagree on the bend radius "
                           f'({s["bend_radius_in"]}" vs {m["bend_radius_in"]}"); both are kept and checks give NEEDS_REVIEW '
                           "unless the outcome is the same under both.")
        rows.append(row)
    return rows


def main():
    src = json.load(open(os.path.join(ROOT, "manufacturers", "sources", "sendcutsend_bending_tables_2026-10-20.json")))
    legacy = json.load(open(os.path.join(ROOT, "tests", "fixtures", "phase1_sendcutsend.json")))
    range_rules = [r for r in legacy["processes"][0]["rules"] if r["type"] == "thickness_range"]
    materials = []
    for tname, mid, name, aliases in MATS:
        materials.append({"id": mid, "name": name, "aliases": aliases,
                          "thickness_specs": build_rows(src["spec_table"][tname], src["minmax_table"][tname])})
    allm = [m[1] for m in MATS]
    bend_src = lambda note: {"url": U_BEND, "date_verified": D, "note": note}
    rules = list(range_rules) + [
        {"id": "scs.thickness_in_stock", "type": "thickness_in_stock", "enabled": True, "verified": True, "severity": "ERROR",
         "parameters": {}, "source": {"url": U_CALC, "also": [U_MINMAX], "date_verified": D,
                                      "note": "Bending specification tables list the stocked thicknesses per material; N/A rows are not bendable."},
         "limitations": "A thickness missing from the table is reported NEEDS_REVIEW (the list may not be exhaustive), only N/A rows FAIL."},
        {"id": "scs.bend_radius_fixed", "type": "bend_radius_match", "enabled": True, "verified": True, "severity": "WARNING",
         "parameters": {"spec": "bend_radius_mm", "tolerance_mm": 0.0127},
         "rationale": "SendCutSend does not offer custom bend radii; radius and K-factor are set per material thickness, so parts must be designed with those values.",
         "source": {"url": U_CALC, "also": [U_BEND, U_MINMAX], "date_verified": D,
                    "note": 'Table "Effective Bend Radius @ 90°". Tolerance 0.0127 mm = half of the last published digit (0.001 in).'},
         "limitations": "Published as the effective radius at 90 degrees; other angles are not separately published."},
        {"id": "scs.min_flange_length", "type": "min_flange_length", "enabled": True, "verified": True, "severity": "ERROR",
         "parameters": {"spec": "min_flange_length_mm", "measure": "apex"},
         "applies_to": {"bend_angle_deg": {"min": 89.0, "max": 91.0}},
         "source": {"url": U_CALC, "also": [U_MINMAX], "date_verified": D,
                    "note": 'Table "Min Formed Flange Length @ 90°" (equals "Min Flange Length (After Bend)" in the min/max chart). The calculator page states formed flange lengths are measured from the apex of the bend.'},
         "limitations": "Published for 90-degree bends only; flanges at other angles give NEEDS_REVIEW. Apex length is computed from the measured tangent length, bend radius and angle."},
        {"id": "scs.feature_to_bend", "type": "min_hole_bend_distance", "enabled": True, "verified": True, "severity": "ERROR",
         "parameters": {"spec": "die_width_mm", "factor": 0.5, "measure": "centerline"},
         "rationale": "Features inside the die width distort during bending (die lines); large cutouts in the die line can also shift the bend.",
         "source": {"url": U_DEFORM, "also": [U_CALC, U_BEND], "date_verified": D,
                    "note": "Keep cut features at least 1/2 the die width away from the centerline of each bend; die width per material/thickness from the bending specifications table."},
         "limitations": "Measured to the bend centerline; the add-in measures to the bend tangent line and bounds the offset, so borderline cases give NEEDS_REVIEW."},
        {"id": "scs.min_hole_diameter", "type": "min_hole_diameter", "enabled": True, "verified": True, "severity": "WARNING",
         "parameters": {"min_ratio_to_thickness": 0.5},
         "rationale": "The pierce needs room; holes smaller than the minimum will distort, char, or fail to cut.",
         "source": {"url": U_CUT, "also": [U_BEND], "date_verified": D,
                    "note": 'Laser cutting: "At least 50% of material thickness" for holes and cutouts. Metals are routed to laser cutting.'},
         "limitations": "The page states the exact minimum varies by material and thickness (listed on each material page, not retrieved); 50% is the general published value."},
        {"id": "scs.max_flat_size", "type": "max_part_dimensions", "enabled": True, "verified": True, "severity": "ERROR",
         "parameters": {"spec": "max_flat_size_mm"},
         "source": {"url": U_MINMAX, "also": [U_BEND], "date_verified": D, "note": "Min/max part sizes for bending: Max Flat Part Size per material and thickness."},
         "limitations": "Needs the flat pattern. Flat size comes from the flat pattern's axis-aligned bounding box."},
        {"id": "scs.min_flat_size", "type": "min_part_dimensions", "enabled": True, "verified": True, "severity": "ERROR",
         "parameters": {"spec": "min_flat_size_mm"},
         "source": {"url": U_MINMAX, "date_verified": D, "note": "Min Flat Part Size per material and thickness."},
         "limitations": "Needs the flat pattern."},
        {"id": "scs.max_bend_length", "type": "max_bend_length", "enabled": True, "verified": True, "severity": "ERROR",
         "parameters": {"spec": "max_bend_length_mm"},
         "source": {"url": U_MINMAX, "date_verified": D, "note": "Max Bend Length per material and thickness."}},
        {"id": "scs.min_hole_edge_distance", "type": "min_hole_edge_distance", "enabled": False, "verified": False, "severity": "ERROR",
         "parameters": {}, "limitations": "No hole-to-edge distance is published in the retrieved SendCutSend pages. Not entered."},
    ]
    prof = {
        "schema_version": 2,
        "manufacturer": {"id": "sendcutsend", "name": "SendCutSend", "website": "https://sendcutsend.com"},
        "profile_status": "partially_verified",
        "description": "Laser cutting + CNC bending of sheet metal. Values are transcribed from SendCutSend's published tables (retrieved 2026-10-20); nothing is inferred.",
        "research": {"status": "partial", "attempted": D,
                     "notes": "Retrieved: bending calculator specs table, processing min/max chart, sheet-cutting, bending and bend-deformation guidelines, mild steel page. "
                              "Not published/retrieved: hole-to-edge distance, feature-to-feature spacing, per-material minimum hole sizes, per-material cut tolerances other than mild steel."},
        "processes": [{
            "id": "sheet_metal_bending", "name": "Laser cutting + CNC bending (sheet metal)",
            "thickness_match_tolerance_mm": 0.05,
            "materials": materials,
            "tolerances": [
                {"id": "scs.tol.laser.mild_steel", "text": "Laser cut tolerance +/-0.005 in across .030-.500 in (mild steel)", "value": 0.127, "units": "mm",
                 "applies_to": "mild_steel", "source": {"url": U_MILD, "date_verified": D}},
                {"id": "scs.tol.bend_angle", "text": "Sheet metal bend angle tolerance +/-1 deg (bends up to 24 in), +/-2 deg (longer)", "value": 1, "units": "deg",
                 "source": {"url": U_BEND, "date_verified": D}},
                {"id": "scs.tol.bend_to_edge", "text": "Bend-to-edge tolerance +/-0.015 in (each additional bend adds at least 0.015 in)", "value": 0.381, "units": "mm",
                 "source": {"url": U_BEND, "date_verified": D}}],
            "restrictions": [
                {"id": "scs.r.channel_ratio", "text": "U/C-channel: base must be at least 2x the flange length (sheet metal).", "modelled": False, "source": {"url": U_BEND, "date_verified": D}},
                {"id": "scs.r.box_flange", "text": "3/4-sided boxes without hardware: max flange length 5 in; flanges 3.5-5 in need min flange width 1.1 in; with hardware max 3.00 in.", "modelled": False, "source": {"url": U_BEND, "date_verified": D}},
                {"id": "scs.r.bend_angles", "text": "Cannot bend: acute angles greater than 130 deg, obtuse angles less than 5 deg; no curl/bump/roll forming, coining or hemming. 'Max bend angle 130 deg' (angle convention not defined on the page, so not modelled).", "modelled": False, "source": {"url": U_BEND, "date_verified": D}},
                {"id": "scs.r.single_body", "text": "STEP/STP uploads must contain a single solid sheet metal body; assemblies/multi-body files must be uploaded as separate files.", "modelled": False, "source": {"url": U_CUT, "date_verified": D}},
                {"id": "scs.r.model_at_spec", "text": "Model at stock thickness with SendCutSend's K-factor and bend radius, or the file can error with open contours.", "modelled": False, "source": {"url": U_CUT, "date_verified": D}},
                {"id": "scs.r.square_relief", "text": "Use square bend reliefs (not tapered/rounded) for STEP uploads.", "modelled": False, "source": {"url": U_CUT, "date_verified": D}}],
            "notes": ["Hole-to-edge, feature-to-feature spacing and per-material hole minimums are not published in the retrieved pages."],
            "rules": rules}]}
    out = os.path.join(ROOT, "manufacturers", "sendcutsend.json")
    json.dump(prof, open(out, "w"), indent=1)
    print("wrote", out)


if __name__ == "__main__":
    main()
