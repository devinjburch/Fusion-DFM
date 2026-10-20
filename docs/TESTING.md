# Testing

`pip install -r requirements-dev.txt && pytest` (44 tests, no Fusion needed):
- `test_profiles.py` – shipped profiles parse; unverified profiles have no enabled rules; invalid profiles rejected.
- `test_engine.py` – PASS/FAIL/NEEDS_REVIEW/SKIPPED behaviour, boundary values, missing-data handling, material matching, SendCutSend cases.
- `test_geometry.py` – vector helpers. `test_bridge_and_bundle.py` – JSON payloads, engine has no CAD import, installer layout, add-in modules compile.

## Manual test in Fusion (required before trusting extraction)
1. Install; run the add-in; confirm button + palette appear and `fusion_dfm.log` is written; Stop removes them.
2. Make a sheet metal part: 1.5 mm steel, flange 10 mm, bend R1.5, hole Ø5 at 3 mm from an edge and 3 mm from a bend; create a flat pattern.
3. Analyze with **DEMO**: expect FAIL on hole-to-edge/bend; click the issue → hole face selected. Compare *Extracted geometry* with Fusion's Measure tool.
4. Remove the flat pattern → max-size rule becomes NEEDS_REVIEW. Use a non-sheet-metal body → warning shown.
5. Analyze with PCBWay/Xometry → everything "not checked", overall NEEDS REVIEW (never PASS).
