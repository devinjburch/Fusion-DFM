# Phase 2 progress

Branch `feature/phase2-manufacturing` (from `feature/phase1-mvp`; Phase 1 unchanged as baseline, all Phase 1 tests still pass).

## Completed
- [x] Manufacturer DB schema v2 + validation tests; SendCutSend rebuilt from published tables (9 metals, per-thickness specs, 1 recorded source conflict)
- [x] Rules: stock thickness, fixed bend radius, apex-measured min flange, feature-to-bend-centerline (½ die width), laser min hole/cutout, min/max flat size, max bend length
- [x] Conflict handling, advisory vs requirement, coverage gaps, never-PASS-on-missing-data, unverified rules never decide
- [x] Multi-manufacturer comparison (verdicts, counts, reasons, corrections) + palette Compare tab
- [x] Geometry: slots, rectangles, irregular cutouts, non-through filtering, multi-body and assembly extraction (documented API only), bend length/zone, flange apex
- [x] Recommendations with measured/required values in mm and in, rationale, source, affected geometry; structured `Correction` model (round-trip tested)
- [x] Reporting: self-contained HTML, issues CSV, comparison CSV, source/limitation sections; export button
- [x] AI redesign architecture: models, approval state machine, mock adapter, undo, example artifact, tests
- [x] Docs: MANUFACTURERS, ARCHITECTURE, AI_ARCHITECTURE, LIMITATIONS, TESTING, API_VERIFICATION

## Remaining / next
- [ ] Run Phase 2 on real Fusion parts (see TESTING.md) and fix extraction surprises (cutouts, assemblies are untested live)
- [ ] PCBWay + Xometry data (needs source text; sites unreachable from the build environment)
- [ ] SendCutSend: per-material hole minimums, hole-to-edge, feature spacing (material pages are JS-rendered)
- [ ] Pick-a-material and pick-a-process in Compare mode (currently auto-detect; Fusion library names like "Steel" don't match)
- [ ] Phase 3 candidates: see the final summary

## Blockers
- PCBWay / Xometry unreachable (proxy 403 / DNS failure on 2026-10-20); documented in MANUFACTURERS.md; not retried.
- No Fusion runtime in the build environment.

## Field-test changes (2026-10-23, from docs/field-reports)
- [x] Hole/feature-near-bend (`scs.feature_to_bend`) is now a non-blocking WARNING (new `consequence` rule field, new WARNING status, "pass with warnings" / conditionally compatible)
- [x] Rule-specific result titles ("Hole 4: too close to bend"), explanation text uses the same CAD labels as the titles
- [x] `scripts/field_report.py` redaction: URL-encoded home path, doubled-backslash (repr) home path, design names in export file names and logs (case-insensitive)
- [ ] Not changed: demo profile's `demo.hole_bend` stays blocking (fictional profile; Phase 1 behaviour preserved). Flip `consequence` there if you want parity.
- [ ] Idea from round 5: disable the Export button while a write is in progress (two identical exports were written 2 s apart)
