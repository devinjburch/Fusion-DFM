"""Fusion *script* (not add-in): runs the Fusion-DFM smoke test. Install with scripts/install.py."""
import os
import sys
import traceback

import adsk.core

_HERE = os.path.dirname(os.path.abspath(__file__))
# installed layout: <API>/Scripts/FusionDFMSmoke  and  <API>/AddIns/FusionDFM
for cand in (os.path.join(_HERE, "..", "..", "AddIns", "FusionDFM"), os.path.join(_HERE, "..", "..")):
    if os.path.isdir(os.path.join(cand, "fusion_addin")):
        sys.path.insert(0, os.path.abspath(cand))
        break


def run(context):
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        from fusion_addin import smoke
        _, report = smoke.run(app)
        ui.messageBox(report, "Fusion-DFM smoke test")
    except Exception:
        msg = traceback.format_exc()
        if ui:
            ui.messageBox("Smoke test crashed:\n" + msg)
