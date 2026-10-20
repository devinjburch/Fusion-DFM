# Architecture

```
Fusion model --extraction.py--> PartModel (mm, geometry-neutral) --engine.evaluate(profile)--> Report --bridge--> palette (HTML)
                                      ^ dfm_engine/models.py                 ^ manufacturers/*.json
```
- `dfm_engine` never imports `adsk`; a test enforces this. A future SOLIDWORKS adapter only needs to produce a `PartModel`.
- **Missing data is never PASS.** `PartModel.unsupported` maps feature → reason; the engine turns affected rules into
  `NEEDS_REVIEW`. Disabled/unverified rules yield `SKIPPED` ("not checked"). Overall PASS needs ≥1 PASS and no FAIL/NEEDS_REVIEW.
- Statuses: `PASS | FAIL | NEEDS_REVIEW | SKIPPED`. Severity: `ERROR | WARNING | INFO` (failures use the rule's severity; review = WARNING).
- Every `RuleResult` carries rule id, severity, geometry ref (Fusion `entityToken`), measured, required, explanation,
  recommendation, source URL, date verified, manufacturer, demo flag.
- Fusion layer: `app_main.py` (lifecycle, button, palette, handlers kept alive in a list), `bridge.py` (pure payload
  builders), `extraction.py`, `highlight.py` (selection via `findEntityByToken`), `log.py` (rotating file log).
- Units: Fusion cm → engine mm at the extraction boundary only.
- Rules: `thickness_range, min_bend_radius, min_flange_length, min_hole_edge_distance, min_hole_bend_distance,
  min_hole_diameter, max_part_dimensions`. Limits may be absolute (`min_mm`) and/or thickness-relative
  (`min_ratio_to_thickness`; the larger applies). Rules may be scoped by `applies_to.materials` / `thickness_mm`.
