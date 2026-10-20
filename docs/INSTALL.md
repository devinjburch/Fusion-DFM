# Installation

1. Python is bundled with Fusion; no pip dependencies are needed at runtime.
2. `python scripts/install.py` builds the bundle `FusionDFM/` (`FusionDFM.py`, `FusionDFM.manifest`, `fusion_addin/`,
   `dfm_engine/`, `manufacturers/`) and copies it into the Fusion AddIns folder:
   - Windows: `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns`
   - macOS: `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns`
   Use `--dest <folder>` to build elsewhere, then copy manually. (The folder/py/manifest names must match; that is why a bundle is assembled.)
3. In Fusion: **Utilities → Add-Ins → Scripts and Add-Ins → Add-Ins**, select **FusionDFM**, **Run** (tick *Run on Startup* if desired).
4. Button **Check Manufacturability** appears in the Design workspace Utilities panel (promoted). It opens the Fusion-DFM palette.
5. Logs: `~/FusionDFM/logs/fusion_dfm.log`. Startup/shutdown failures also show a message box.

Workflow: pick manufacturer → process → (optionally) material → **Analyze active design**. If a body is selected it is
analysed; otherwise the sheet metal body (largest if several). Click a failing item to select that geometry in Fusion.
