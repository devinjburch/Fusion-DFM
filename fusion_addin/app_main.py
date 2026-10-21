"""Add-in lifecycle: toolbar button, palette, event wiring. Fusion-only module."""
import json
import os
import pathlib
import traceback
import webbrowser

import adsk.core
import adsk.fusion

from . import bridge, extraction, highlight
from .log import LOG_FILE, get_logger

CMD_ID = "FusionDFM_CheckCmd"
PALETTE_ID = "FusionDFM_Palette"
# Panels tried in order. IDs are NOT documented by Autodesk; the first existing one is used and
# every panel id Fusion reports is written to the log at startup (see docs/API_VERIFICATION.md).
PANEL_CANDIDATES = ("SolidScriptsAddinsPanel",)
HTML_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "index.html")

_log = get_logger()
_handlers = []          # event handlers must stay referenced or Fusion drops them
_last = {}              # last analysis: {"parts": [...], "warnings": [...], "request": {...}} for report export
_app = None
_ui = None
_panel_id = None


def _keep(h):
    _handlers.append(h)
    return h


def _send(action, payload):
    pal = _ui.palettes.itemById(PALETTE_ID)
    if pal is None:
        _log.error("cannot send %r: palette missing", action)
        return
    pal.sendInfoToHTML(action, json.dumps(payload))


class _HtmlHandler(adsk.core.HTMLEventHandler):
    def notify(self, args):
        _log.info("palette -> python: action=%s data=%.200s", args.action, args.data)
        try:
            data = json.loads(args.data) if args.data else {}
            if args.action == "ready":
                _log.info("palette page loaded and reported ready")
                _send("profiles", bridge.profiles_payload())
            elif args.action == "run":
                self._run(data)
            elif args.action == "compare":
                self._compare(data)
            elif args.action == "export":
                self._export()
            elif args.action == "open_file":
                self._open_file(data.get("path", ""))
            elif args.action == "open_url":
                url = data.get("url", "")
                if url.startswith("https://"):
                    webbrowser.open(url)
            elif args.action == "highlight":
                n = highlight.highlight(_app, data.get("tokens", []))
                _log.info("highlighted %d entities", n)
                _send("highlighted", {"count": n})
        except Exception as e:
            _log.error("palette event %s failed:\n%s", args.action, traceback.format_exc())
            _send("error", {"message": f"{e.__class__.__name__}: {e}  (details in {LOG_FILE})"})

    def _run(self, req):
        try:
            part, warnings = extraction.extract_part(_app)
        except extraction.ExtractionError as e:
            _log.info("analysis not possible: %s", e)
            _send("error", {"message": str(e)})
            return
        payload = bridge.results_payload(part, warnings, req)
        _last.update(parts=[part], warnings=warnings, request={"manufacturers": [{"id": req.get("manufacturer_id"),
                     "process_id": req.get("process_id"), "material_id": req.get("material_id")}]})
        _log.info("analysis %s/%s -> %s %s", req.get("manufacturer_id"), req.get("process_id"),
                  payload["overall"], payload["counts"])
        _send("results", payload)


def _model_name():
    design = adsk.fusion.Design.cast(_app.activeProduct)
    doc = _app.activeDocument.name if _app.activeDocument else ""
    return design.rootComponent.name if design else "", doc


def _compare(self, req):
    try:
        if req.get("all_parts", True):
            parts, warnings = extraction.extract_all(_app)
        else:
            part, warnings = extraction.extract_part(_app)
            parts = [part]
    except extraction.ExtractionError as e:
        _log.info("comparison not possible: %s", e)
        _send("error", {"message": str(e)})
        return
    payload = bridge.compare_payload(parts, warnings, req)
    _last.update(parts=parts, warnings=warnings, request=req)
    _log.info("comparison of %d part(s): %s", len(parts),
              [(e["manufacturer_id"], e["verdict"]) for e in payload["comparison"]["entries"]])
    _send("compare_results", payload)


def _export(self):
    if not _last:
        _send("error", {"message": "Run an analysis before exporting a report."})
        return
    name, doc = _model_name()
    res = bridge.export_payload(_last["parts"], _last["warnings"], _last["request"], name, doc)
    _log.info("report written: %s", res["paths"])
    _send("exported", res)


def _open_file(self, path):
    reports = os.path.join(os.path.expanduser("~"), "FusionDFM", "reports")
    full = os.path.abspath(path)
    if full.startswith(os.path.abspath(reports) + os.sep) and full.endswith(".html") and os.path.exists(full):
        webbrowser.open(pathlib.Path(full).as_uri())     # only files this add-in wrote


_HtmlHandler._compare, _HtmlHandler._export, _HtmlHandler._open_file = _compare, _export, _open_file


class _CmdCreated(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        _log.info("Check Manufacturability button clicked")
        try:
            show_palette()
        except Exception:
            _log.error("show palette failed:\n%s", traceback.format_exc())
            _ui.messageBox(f"Fusion-DFM could not open its panel.\nSee {LOG_FILE}")


def show_palette():
    pal = _ui.palettes.itemById(PALETTE_ID)
    if pal is None:
        url = pathlib.Path(HTML_PATH).as_uri()
        _log.info("creating palette from %s (exists=%s)", url, os.path.exists(HTML_PATH))
        # Palettes.add(id, name, htmlFileURL, isVisible, showCloseButton, isResizable, width, height, useNewWebBrowser)
        pal = _ui.palettes.add(PALETTE_ID, "Fusion-DFM", url, True, True, True, 440, 700, False)
        if pal is None:
            raise RuntimeError("Palettes.add returned null")
        pal.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateRight
        pal.incomingFromHTML.add(_keep(_HtmlHandler()))
    pal.isVisible = True


def _find_panel():
    ids = [p.id for p in _ui.allToolbarPanels]
    _log.info("toolbar panels reported by Fusion (%d): %s", len(ids), ids)
    for pid in PANEL_CANDIDATES:
        panel = _ui.allToolbarPanels.itemById(pid)
        if panel:
            return panel
    return None


def start():
    global _app, _ui, _panel_id
    _app = adsk.core.Application.get()
    _ui = _app.userInterface
    _log.info("=== Fusion-DFM starting; Fusion version %s; log %s", _app.version, LOG_FILE)
    # CommandDefinitions.addButtonDefinition(id, name, tooltip[, resourceFolder])
    cmd = _ui.commandDefinitions.itemById(CMD_ID)
    if cmd is not None:
        cmd.deleteMe()  # stale definition from an earlier crashed run
    cmd = _ui.commandDefinitions.addButtonDefinition(
        CMD_ID, "Check Manufacturability",
        "Check this sheet metal design against a manufacturer's design rules")
    cmd.commandCreated.add(_keep(_CmdCreated()))
    panel = _find_panel()
    if panel is None:
        _log.error("no candidate toolbar panel found; opening palette directly")
        _ui.messageBox("Fusion-DFM: could not find a toolbar panel for the button.\n"
                       f"The panel will open directly instead. Panel ids are in {LOG_FILE}.")
        show_palette()
        return
    _panel_id = panel.id
    ctl = panel.controls.itemById(CMD_ID)
    if ctl is None:
        ctl = panel.controls.addCommand(cmd)
    ctl.isPromoted = True
    _log.info("button added to panel %r", _panel_id)


def stop():
    global _handlers
    _log.info("=== Fusion-DFM stopping")
    if _ui:
        for what, fn in (("palette", lambda: _ui.palettes.itemById(PALETTE_ID)),
                         ("control", lambda: _ui.allToolbarPanels.itemById(_panel_id).controls.itemById(CMD_ID)
                          if _panel_id else None),
                         ("command", lambda: _ui.commandDefinitions.itemById(CMD_ID))):
            try:
                obj = fn()
                if obj:
                    obj.deleteMe()
            except Exception:
                _log.error("cleanup of %s failed:\n%s", what, traceback.format_exc())
    _handlers = []
