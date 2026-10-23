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

## PCBWay — unverified (blocked)
`https://www.pcbway.com`: requests failed (proxy 403 with curl; DNS resolution failure from the web-fetch tool) on 2026-10-20. Not retried.
Profile has no materials and all rules disabled; results are NEEDS_REVIEW. To complete: save the official sheet-metal capabilities/design-guide pages
(HTML or PDF) into the repo (or paste the text) and enter values with `source.url` + `source.date_verified`.

## Xometry — unverified (blocked)
`https://www.xometry.com`: same failure modes as above. Same completion steps.

## Demo — fictional
`manufacturers/demo.json`: invented values, labelled DEMO everywhere; excluded from ranking by default in comparisons.

## Verification rules enforced by tests
Every enabled rule in a non-demo profile must be `verified` with an https `source.url` and `date_verified`; every thickness row, tolerance and
restriction needs a source; disabled rules must explain why; unverified profiles cannot contain enabled rules or invented materials.
