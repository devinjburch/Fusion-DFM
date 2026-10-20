"""Add-in lifecycle: toolbar button, palette, event wiring. Fusion-only module."""
import json
import os
import traceback

import adsk.core
import adsk.fusion

from . import bridge, extraction, highlight
from .log import get_logger

CMD_ID = "FusionDFM_CheckCmd"
PALETTE_ID = "FusionDFM_Palette"
PANEL_ID = "SolidScriptsAddinsPanel"          # Design workspace > Utilities
HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "index.html")

_log = get_logger()
_handlers = []          # keep references alive; Fusion does not
_app = None
_ui = None


def _keep(h):
    _handlers.append(h)
    return h


def _send(action, payload):
    pal = _ui.palettes.itemById(PALETTE_ID)
    if pal:
        pal.sendInfoToHTML(action, json.dumps(payload))


class _HtmlHandler(adsk.core.HTMLEventHandler):
    def notify(self, args):
        try:
            data = json.loads(args.data) if args.data else {}
            if args.action == "ready":
                _send("profiles", bridge.profiles_payload())
            elif args.action == "run":
                self._run(data)
            elif args.action == "open_url":
                url = data.get("url", "")
                if url.startswith("https://"):
                    adsk.core.Application.get().openExternalWebBrowser(url)
            elif args.action == "highlight":
                n = highlight.highlight(_app, data.get("tokens", []))
                _send("highlighted", {"count": n})
        except Exception as e:
            _log.error("palette event failed: %s", traceback.format_exc())
            _send("error", {"message": str(e) or e.__class__.__name__})

    def _run(self, req):
        try:
            part, warnings = extraction.extract_part(_app)
        except extraction.ExtractionError as e:
            _send("error", {"message": str(e)})
            return
        payload = bridge.results_payload(part, warnings, req)
        _log.info("analysis %s/%s -> %s", req.get("manufacturer_id"), req.get("process_id"), payload["overall"])
        _send("results", payload)


class _CmdCreated(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        try:
            _show_palette()
        except Exception:
            _log.error("show palette failed: %s", traceback.format_exc())
            _ui.messageBox("Fusion-DFM could not open its panel. See ~/FusionDFM/logs/fusion_dfm.log")


def _show_palette():
    pal = _ui.palettes.itemById(PALETTE_ID)
    if pal is None:
        pal = _ui.palettes.add(PALETTE_ID, "Fusion-DFM", HTML.replace("\\", "/"), True, True, True, 440, 700)
        pal.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateRight
        pal.incomingFromHTML.add(_keep(_HtmlHandler()))
    pal.isVisible = True


def start():
    global _app, _ui
    _app = adsk.core.Application.get()
    _ui = _app.userInterface
    _log.info("starting")
    cmd = _ui.commandDefinitions.itemById(CMD_ID)
    if cmd is None:
        cmd = _ui.commandDefinitions.addButtonCommand(
            CMD_ID, "Check Manufacturability",
            "Check this sheet metal design against a manufacturer's design rules", "")
    cmd.commandCreated.add(_keep(_CmdCreated()))
    panel = _ui.allToolbarPanels.itemById(PANEL_ID)
    if panel and panel.controls.itemById(CMD_ID) is None:
        panel.controls.addCommand(cmd).isPromoted = True


def stop():
    global _handlers
    _log.info("stopping")
    if _ui:
        pal = _ui.palettes.itemById(PALETTE_ID)
        if pal:
            pal.deleteMe()
        panel = _ui.allToolbarPanels.itemById(PANEL_ID)
        ctl = panel.controls.itemById(CMD_ID) if panel else None
        if ctl:
            ctl.deleteMe()
        cmd = _ui.commandDefinitions.itemById(CMD_ID)
        if cmd:
            cmd.deleteMe()
    _handlers = []
