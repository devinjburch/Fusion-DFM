# First-run test procedure (about 10 minutes)

Before starting, have ready a sheet metal part: Design workspace → Sheet Metal tab, a flange or two with a bend, one round hole,
a flat pattern (Create Flat Pattern). Any steel/aluminium material.

1. **Install** per [INSTALL.md](INSTALL.md). Open `C:\Users\<you>\FusionDFM\logs\fusion_dfm.log` in a text editor.
2. **Run the add-in** (Shift+S → Add-Ins → FusionDFM → Run). Expected: no error dialog; log shows
   `=== Fusion-DFM starting`, a list `toolbar panels reported by Fusion`, and `button added to panel 'SolidScriptsAddinsPanel'`.
   - Message box "could not find a toolbar panel" → the panel id guess is wrong; the palette opens anyway. **Send me the log line with the panel ids.**
   - Add-in missing from the list or fails to load → send the error text; likely the `.manifest` (see API_VERIFICATION.md).
3. **Find the button**: Design workspace → Utilities (or Solid) tab → "Check Manufacturability" (promoted).
4. **Click it.** The Fusion-DFM palette should dock on the right with manufacturer/process/material lists.
   Log: `creating palette from file:///...` then `palette page loaded and reported ready`.
   - Blank palette / no "ready" line → the `file:///` URL assumption failed. Send the log.
5. **Smoke test**: Shift+S → **Scripts** tab → **FusionDFMSmoke** → Run (palette left open, sheet metal part open). A message box lists
   each check as OK/WARN/FAIL (also saved to `FusionDFM\logs\smoke_report.txt`): `fusion_api, command_defined, toolbar_button,
   active_design, sheet_metal_body, thickness_rule, thickness_geometry, extract_part, evaluate_demo, results_display`.
   Compare `thickness_rule` with the thickness in your sheet metal rule, and holes/bends counts with your part.
6. **Analyze**: in the palette choose *DEMO Manufacturer*, **Analyze active design**. Expect a DEMO banner, counts, and
   "Extracted geometry" matching the part (thickness, hole Ø, bend radius, flat size). Try *SendCutSend* with the matching material.
7. **Highlight**: with the DEMO profile on a part with a failing/passing hole result, click an item → that hole/bend/flange face
   should become selected in the model. Log: `highlighted N entities`.
8. **Stop** the add-in (Shift+S → Stop): button and palette disappear; log shows `stopping`. Run again to confirm it restarts.

**Send me** (any failures): `fusion_dfm.log`, `smoke_report.txt`, your Fusion version (Help → About), and whether your Fusion API folder is
`Autodesk Fusion` or `Autodesk Fusion 360`.
