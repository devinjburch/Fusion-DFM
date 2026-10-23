# Testing

## Automated (no Fusion needed)
`pip install -r requirements-dev.txt && python -m pytest -q` (160+ tests):
`test_database.py` (profile integrity, sources, conflicts, units) · `test_engine.py` (Phase 1 semantics) · `test_phase2_engine.py` (SendCutSend v2 rules, thickness matching,
boundaries, conflicts, advisory) · `test_compare.py` (verdict logic) · `test_features.py` (cutout classification, de-duplication) · `test_extraction_fake.py` (extraction + smoke runner
against a fake `adsk`: L-bracket, plates with slot/rect/irregular/pocket loops, assemblies) · `test_recommendations.py` (messages, correction round-trips) ·
`test_reporting.py` · `test_ai_architecture.py` · `test_backward_compat.py` · `test_bridge_and_bundle.py` (payloads, installer, compile checks).
The fake `adsk` validates OUR logic only; it cannot prove Fusion behaves the same.

## Local Fusion testing
Install per [INSTALL.md](INSTALL.md) (re-run `python scripts\install.py`, restart the add-in), then run [FIRST_RUN.md](FIRST_RUN.md) (Phase 1 checks must still pass) and:

### Phase 2 checklist
1. **Smoke test** (Shift+S → Scripts → FusionDFMSmoke) now has 13 checks. New ones: `extract_all_parts`, `compare_all`, `export_report`. Send me the message box text.
2. **Compare tab**: open the standoff part → *Compare manufacturers*. Expect SendCutSend with a verdict (probably *Conditionally compatible* or *Incompatible* with specific reasons),
   PCBWay and Xometry *Needs review* with a "blocked" data note. Click a failure → geometry highlights.
3. **Rules to eyeball on your part** (SendCutSend, Mild Steel 0.100 in / 2.54 mm — note 0.100 in is NOT a listed mild steel gauge, so expect *NEEDS_REVIEW: not a listed stock thickness*):
   - Bend radius vs the fixed radius table; flange apex length vs the table; feature-to-bend centerline (NEEDS_REVIEW when borderline).
   - To exercise PASS paths, set the sheet metal rule to a listed gauge (e.g. 0.119 in mild steel, radius 0.063 in).
4. **Cutouts**: add a slot, a rectangular cutout and an irregular (spline) cutout; analyze → *Extracted geometry* should list cutouts; slot/rect sizes should match Measure; the spline cutout must be NEEDS_REVIEW.
   Add a shallow pocket/emboss: it must NOT appear as a cutout (check the log line `ignored inner loop`).
5. **Assembly**: put two sheet metal parts (one inserted twice) in an assembly → compare with *Analyze all visible sheet metal bodies*: expect one entry per distinct body, `×2` for the repeated one.
6. **Export**: click *Export report (HTML + CSV)* → files in `C:\\Users\\<you>\\FusionDFM\\reports\\`; open the HTML link: check comparison table, sources, limitations section.
7. Logs: `~/FusionDFM/logs/fusion_dfm.log` records face census, classification and ignored loops; send it with any surprise.

8. Package the results: `python scripts\field_report.py --run-tests` and commit the file (see [FIELD_TESTING.md](FIELD_TESTING.md)).
