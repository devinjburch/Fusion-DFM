"""Fusion add-in entry point. The installer copies this next to the packages as FusionDFM.py."""
import os
import sys
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import adsk.core  # noqa: E402

_started = False


def run(context):
    global _started
    try:
        from fusion_addin import app_main
        app_main.start()
        _started = True
    except Exception:
        _report("Fusion-DFM failed to start")


def stop(context):
    global _started
    try:
        from fusion_addin import app_main
        app_main.stop()
    except Exception:
        _report("Fusion-DFM failed to stop cleanly")
    _started = False
    # Fusion keeps one Python interpreter alive: drop our modules so a re-Run loads fresh code.
    for name in [m for m in sys.modules if m.split(".")[0] in ("fusion_addin", "dfm_engine")]:
        del sys.modules[name]


def _report(title):
    msg = f"{title}:\n{traceback.format_exc()}"
    try:
        from fusion_addin.log import get_logger
        get_logger().error(msg)
    except Exception:
        pass
    try:
        ui = adsk.core.Application.get().userInterface
        if ui:
            ui.messageBox(msg)
    except Exception:
        pass
