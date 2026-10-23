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


# Phase 2 additions
```
Fusion ──extract_all──► [PartModel…] ──compare(profiles)──► Comparison ──bridge──► palette (Single | Compare)
                              │                  │                         └──► reporting: HTML + CSV (self-contained)
                              │                  └─ engine.evaluate ► Report ► RuleResult ► Correction (data only)
                              └─ features.classify_loop (CAD-free) for slots / rectangles / irregular cutouts
ai_assistant/: ManufacturingProblem → SuggestedCorrection → approval → CadAdapter (mock only) → re-analysis → accept | undo
```
- **Schema v2 profiles** (`dfm_engine/profile.py`): per-thickness `thickness_specs` tables with optional `conflicts`; spec-driven rules
  (`parameters.spec`, `factor`, `measure`); `strength` (requirement/advisory); `applies_to` by material, thickness, bend angle, feature kind;
  `tolerances`, `restrictions`, `research` status. v1 profiles still load.
- **Thickness matching**: a part thickness matches a listed stock thickness within `thickness_match_tolerance_mm` (default 0.05 mm). Unlisted -> NEEDS_REVIEW
  (never silently rounded); explicitly N/A rows -> FAIL.
- **Verdicts** (`dfm_engine/compare.py`): INCOMPATIBLE (any confirmed FAIL) > NEEDS_REVIEW (unresolved or no verified check ran) >
  CONDITIONALLY_COMPATIBLE (nothing failed, but a core category such as hole-to-edge has no verified rule) > COMPATIBLE (all core categories covered and passed).
- **Centerline rule**: the add-in measures feature-to-bend-*tangent* distance and bounds the tangent→centerline offset by `(R_inner + t)·angle/2`;
  PASS only if the lower bound already satisfies the requirement, FAIL only if even the upper bound cannot, otherwise NEEDS_REVIEW.
- **Apex flange length**: `L_tangent + (R_inner + t)·tan(angle/2)`, only for single-bend (terminal) flanges with a known angle.
- **Corrections** (`dfm_engine/corrections.py`) are data (`kind, parameter, current, proposed, delta, confidence, side_effects`); nothing applies them.
- **Isolation of uncertain Fusion code**: loop → descriptor conversion is in `extraction.py`; all classification lives in CAD-free `dfm_engine/features.py`
  and is tested with synthetic fixtures and a fake `adsk` (`tests/fake_adsk.py`).
- Reports: `dfm_engine/reporting.py` (HTML with inline CSS only; CSV; never overwrites existing files). Files go to `~/FusionDFM/reports/`.

- **WARNING status / verdicts (after field round 5)**: INCOMPATIBLE (any FAIL) > NEEDS_REVIEW (unresolved or nothing verified) > CONDITIONALLY_COMPATIBLE (warnings and/or unverified core categories) > COMPATIBLE.
  Single-manufacturer overall: FAIL > NEEDS_REVIEW > WARNING ("pass with warnings") > PASS. `RuleResult.counts()` gained a `WARNING` key (Phase 1 keys unchanged).
