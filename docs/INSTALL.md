# Installation (Windows)

Add-in location after install: `%APPDATA%\Autodesk\Autodesk Fusion\API\AddIns\FusionDFM`
(typically `C:\Users\<you>\AppData\Roaming\Autodesk\Autodesk Fusion\API\AddIns\FusionDFM`);
smoke-test script: `...\API\Scripts\FusionDFMSmoke`. Logs: `C:\Users\<you>\FusionDFM\logs\fusion_dfm.log`.

## Option A – installer (needs Python 3.9+ from python.org, or `py` launcher)
1. Close Fusion. Open PowerShell in the repo folder.
2. `python scripts\install.py --dry-run` – shows the target folders. Then `python scripts\install.py`.
   If it says it cannot find the API folder, start Fusion once, or pass `--api-dir "C:\Users\<you>\AppData\Roaming\Autodesk\Autodesk Fusion\API"`.
   (Older installs use `Autodesk Fusion 360` instead of `Autodesk Fusion`; the installer checks both.)
3. Start Fusion.

## Option B – manual (no Python needed)
1. In `%APPDATA%\Autodesk\Autodesk Fusion\API\AddIns` create folder `FusionDFM`.
2. Copy the repo folders `fusion_addin`, `dfm_engine`, `manufacturers` into it.
3. **Move** `FusionDFM.py` and `FusionDFM.manifest` out of `FusionDFM\fusion_addin\` up into `FusionDFM\`.
4. Smoke test: create `...\API\Scripts\FusionDFMSmoke` and copy the contents of the repo's `smoke_test\` folder into it.

## Run
Fusion: **Shift+S** (Utilities → Add-Ins → Scripts and Add-Ins) → **Add-Ins** tab → **FusionDFM** → **Run**.
Re-installing: Stop the add-in first, re-run the installer, Run again. Follow [FIRST_RUN.md](FIRST_RUN.md).
