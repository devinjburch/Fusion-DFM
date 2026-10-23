# Manufacturer sources and verification status

All values below were retrieved **2026-10-20** from the manufacturer's own pages. Nothing is inferred from general advice.
Profiles live in `manufacturers/*.json` (schema in [PROFILES.md](PROFILES.md)); the SendCutSend tables are extracted by
`scripts/extract_scs_tables.py` and built into the profile by `scripts/build_scs_profile.py`; the extracted numbers are kept in
`manufacturers/sources/sendcutsend_bending_tables_2026-10-20.json`.

## SendCutSend — partially verified (sheet metal: laser cutting + CNC bending)
| Item | Value / source | Used as |
|---|---|---|
| Per-material, per-thickness bending table (9 metals): K-factor, bend deduction, effective bend radius @90°, die width, min formed flange @90°, min corner relief distance, bend relief depth | https://sendcutsend.com/bending-calculator/ ("Bending specifications per material") | `thickness_specs` rows; rules below |
| Min/max flat part size, max bend length, min flange (flat pattern / after bend), effective radius per thickness | https://sendcutsend.com/materials/processing-min-max/ ("Min/max part sizes for bending") | specs; cross-check of the table above |
| Available thickness ranges per material | https://sendcutsend.com/guidelines/bending/ | `thickness_range` rules |
| Bend radius/K-factor are fixed per material thickness; no custom radii | calculator + bending pages | rule `scs.bend_radius_fixed` (WARNING) |
| Formed flange lengths are measured from the bend apex | calculator page text | rule `scs.min_flange_length` (`measure: apex`, 90° bends only) |
| Keep cut features >= 1/2 die width from each bend centerline; features in the die area "are subject to distorting" and SendCutSend shows a "feature distortion caution area" at checkout (it does not say the part is rejected) | https://sendcutsend.com/guidelines/bend-deformation/ | rule `scs.feature_to_bend`, **non-blocking WARNING** (`consequence: warning`, per user decision 2026-10-23, consistent with the source's wording) |
| Holes/cutouts >= 50% of material thickness (laser; metals are laser cut) | https://sendcutsend.com/guidelines/sheet-cutting/ | rule `scs.min_hole_diameter` (WARNING; page says exact minimum varies per material) |
| Tolerances: laser +/-0.005 in (mild steel page), bend angle +/-1° (<=24 in), bend-to-edge +/-0.015 in | material / bending pages | recorded in `tolerances`, not evaluated |
| Restrictions (U/C-channel 2:1, box flange limits, angle limits, single-body STEP, model at stock specs, square reliefs) | bending + sheet-cutting pages | recorded in `restrictions` (`modelled: false`) |

**Conflicts recorded, not resolved:** 5052 aluminum .080 in bend radius is .038 in in the calculator table but .045 in in the min/max
table; both are stored and the engine returns NEEDS_REVIEW unless the outcome is identical under both. (Polycarbonate rows also disagree
on one thickness; polycarbonate is not sheet metal and is not imported.)

**Not published in the retrieved pages (left disabled / absent):** hole-to-edge distance, feature-to-feature spacing, per-material minimum hole
sizes (stated to live on each material page, which are JavaScript-rendered/not retrieved), per-material cut tolerances other than mild steel,
a definition of "max bend angle 130°". Hence the profile reports coverage gap `hole_edge_distance`, and comparison verdicts for SendCutSend are
at best CONDITIONALLY_COMPATIBLE.

## PCBWay — provisional (owner-supplied research snapshot, 2026-10-23)
Source: `manufacturers/sources/pcbway_buildability_rules_v1_2026-10-23.json` + `manufacturing_buildability_reference_2026-10-23.md` (supplied by the project owner, compiled by an external research session;
this project's build environment cannot reach pcbway.com). The snapshot itself says its PCBWay entries are provisional and must be rechecked against the primary pages, so **every rule is flagged
`provisional` and non-blocking**: it can raise warnings / review items and support "conditionally compatible", but can never fail a part or establish "compatible" (provisional rules do not count toward
requirement coverage). Built by `scripts/build_pcbway_xometry_profiles.py`, which reads each threshold from the saved JSON (no retyping) and is checked by tests.
| Rule | Value (source rule) | Consequence |
|---|---|---|
| `pcb.min_flange` | flange >= 4 x thickness, measured from the bend tangent line (datum unpublished; conservative) (PCB-BEND-002) | warning |
| `pcb.feature_to_bend` | hole/cutout edge to bend line >= 2 x thickness, measured to the bend centerline (PCB-BEND-004) | warning |
| `pcb.min_part` | finished part >= 3 x 3 mm, compared with the flat size (PCB-BEND-001) | review |
| `pcb.stock.<family>` | raw stock minus 5 mm margin per edge: steel/stainless 2990 x 1490, aluminum/titanium 2430 x 1210, copper 1490 x 590 mm (PCB-SHEET-*, PCB-STOCK-EDGE); raw-stock limit, not a finished-part guarantee | review |
| `cnc_routing` process | min part 2 mm, max part 1000 mm, min diameter 0.3 mm (PCB-CUT-005..007); applicability to metal not stated | review |
Not evaluated (listed under "Published requirements not evaluated"): hardware insertion rules (PCB-HW-*), file validation (single solid body, no pre-nested parts, closed profiles), routing corner/dogbone/perforation/tab rules, bend angle review, flange support for 0.187/0.250 in.
**Disabled, conflict preserved:** a second PCBWay article states minimum flange = inside radius + 4T (stricter than 4T); recorded as `pcb.min_flange_radius_plus_4t`, not chosen. No universal minimum bend radius is applied (PCBWay says it depends on material, temper, thickness, grain and tooling).
Unresolved per the snapshot: min hole size by material/process, thickness catalog by alloy, CNC tolerance tables, countersink/counterbore, tapping, bend radius per alloy/temper, PEM dimensions, bend-line vs tangent datum, laser kerf.

## Xometry — provisional (owner-supplied research snapshot, 2026-10-23)
Source: `manufacturers/sources/xometry_buildability_rules_v1_2026-10-23.json` (same provenance and treatment as PCBWay; rules are multiples of material thickness so they apply to any material).
| Rule | Value (source rule) | Consequence |
|---|---|---|
| `xom.min_bend_radius` | inside radius >= 1 x thickness, an inside-radius recommendation (XOM-SM-001) | warning |
| `xom.hole_edge` | hole edge to part edge >= 2 x thickness, edge-to-edge (XOM-SM-002) | warning |
| `xom.thickness_typical` | typical sheet 0.024-0.250 in; thinner/thicker by review (XOM-CAP-001/002) | review |
| `xom.max_blank` | nominal 5 x 10 ft blank (60 x 120 in); larger on request (XOM-CAP-003/004) | review |
| tolerance | automatic quoting as tight as +/-0.005 in for some dimensions (XOM-CAP-005) | recorded only |
Not automated, recorded as restrictions: hole-to-hole 6T (center vs edge unstated; publisher says not to automate), feature-to-countersink 8T, countersink depth 0.6T, relief cuts 1T, corner fillet 0.5T. `xom.bend_to_hole` (6T, bend-edge datum ambiguous) is a disabled rule. CNC tips (XOM-CNC-001..008) are restrictions of a separate `cnc_machining` process (no rules).

**Promoting to verified:** re-check a rule against the cited page, then drop `provisional` (and set a real `date_verified`); rules with consequence `warning`/`review` stay non-blocking unless you change them.
The supplied `.docx` is the same content as the `.md` and is not stored.

## Demo — fictional
`manufacturers/demo.json`: invented values, labelled DEMO everywhere; excluded from ranking by default in comparisons.

## Verification rules enforced by tests
Every enabled rule in a non-demo profile must be `verified` with an https `source.url` and `date_verified`; every thickness row, tolerance and
restriction needs a source; disabled rules must explain why; unverified profiles cannot contain enabled rules or invented materials.
