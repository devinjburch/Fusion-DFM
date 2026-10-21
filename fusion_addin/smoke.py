"""Fusion integration smoke test. Run via the FusionDFMSmoke *script* (see docs/FIRST_RUN.md)."""
from __future__ import annotations
import json
import os
import traceback

import adsk.core
import adsk.fusion

from . import bridge, extraction
from .log import LOG_DIR, get_logger

log = get_logger()
OK, WARN, FAIL = "OK", "WARN", "FAIL"


def run_checks(checks):
    """checks: list of (name, fn). fn returns detail str, or (status, detail). Exceptions -> FAIL."""
    results = []
    for name, fn in checks:
        try:
            r = fn()
            status, detail = (r if isinstance(r, tuple) else (OK, r))
        except Exception as e:
            status, detail = FAIL, f"{e.__class__.__name__}: {e}\n{traceback.format_exc()}"
        log.info("smoke %-22s %s %s", name, status, str(detail).splitlines()[0] if detail else "")
        results.append((name, status, detail))
    return results


def format_report(results) -> str:
    lines = [f"{s:<4} {n}: {d}" for n, s, d in results]
    bad = sum(1 for _, s, _ in results if s == FAIL)
    lines.append(f"\n{len(results) - bad}/{len(results)} checks without failure.")
    return "\n".join(lines)


def build_checks(app):
    ui = app.userInterface
    state = {}

    def fusion_api():
        return f"Fusion {app.version}"

    def command_defined():
        from .app_main import CMD_ID
        return OK if ui.commandDefinitions.itemById(CMD_ID) else (FAIL, "command definition missing - is the FusionDFM add-in running?")

    def toolbar_button():
        from .app_main import CMD_ID
        for p in ui.allToolbarPanels:
            ctl = p.controls.itemById(CMD_ID)
            if ctl:
                return f"button in panel '{p.id}', promoted={ctl.isPromoted}"
        return FAIL, "no toolbar panel contains the button"

    def active_design():
        d = adsk.fusion.Design.cast(app.activeProduct)
        if d is None:
            return FAIL, "no active Design (open a design in the Design workspace)"
        state["design"] = d
        return f"design '{d.rootComponent.name}'"

    def sheet_metal_body():
        d = state["design"]
        bodies = [b for b in d.rootComponent.bRepBodies if b.isSolid]
        for o in d.rootComponent.allOccurrences:
            bodies += [b for b in o.bRepBodies if b.isSolid]
        sm = [b for b in bodies if b.isSheetMetal]
        info = ", ".join(f"{b.name}(sheetMetal={b.isSheetMetal})" for b in bodies) or "none"
        if not sm:
            return FAIL, f"no sheet metal body. Bodies: {info}"
        state["body"] = sm[0]
        return f"{len(sm)} sheet metal body(ies). Bodies: {info}"

    def thickness_rule():
        comp = state["body"].parentComponent
        rule = comp.activeSheetMetalRule
        if rule is None:
            return WARN, "activeSheetMetalRule is null"
        try:
            t = rule.thickness
            state["t_rule_cm"] = t.value
            return f"rule '{rule.name}': thickness {t.value * 10:.4f} mm (expression '{t.expression}')"
        except RuntimeError as e:
            return WARN, (f"rule '{rule.name}' thickness not readable ({e}); happens in the flat pattern "
                          "environment - extraction falls back to geometry. Finish/exit the flat pattern to test the rule.")

    def thickness_geometry():
        t = extraction._thickness_from_geometry(state["body"])
        if t is None:
            return WARN, "could not derive thickness from geometry"
        if "t_rule_cm" in state and abs(t - state["t_rule_cm"] * 10) > 0.02 * t:
            return WARN, f"geometry {t:.4f} mm differs from rule {state['t_rule_cm'] * 10:.4f} mm"
        return f"geometry-derived {t:.4f} mm"

    def extract():
        part, warnings = extraction.extract_part(app)
        state["part"], state["warnings"] = part, warnings
        return (f"thickness={part.thickness_mm} mm ({part.thickness_source}), material={part.material_name}, "
                f"holes={len(part.holes)}, bends={len(part.bends)}, flanges={len(part.flanges)}, "
                f"flat={part.flat_dimensions_mm}, unsupported={sorted(part.unsupported)}, warnings={warnings}")

    def evaluate():
        d = bridge.results_payload(state["part"], state["warnings"],
                                   {"manufacturer_id": "demo", "process_id": "sheet_metal_bending"})
        state["payload"] = d
        json.dumps(d)
        return f"demo profile -> {d['overall']} {d['counts']}"

    def results_display():
        from .app_main import PALETTE_ID
        pal = ui.palettes.itemById(PALETTE_ID)
        if pal is None:
            return WARN, "palette not open - click 'Check Manufacturability' once, then re-run to test display"
        pal.sendInfoToHTML("results", json.dumps(state["payload"]))
        return "results sent to the palette - confirm it now shows the DEMO report"

    return [("fusion_api", fusion_api), ("command_defined", command_defined), ("toolbar_button", toolbar_button),
            ("active_design", active_design), ("sheet_metal_body", sheet_metal_body),
            ("thickness_rule", thickness_rule), ("thickness_geometry", thickness_geometry),
            ("extract_part", extract), ("evaluate_demo", evaluate), ("results_display", results_display)]


def run(app):
    """Run all checks; later checks depending on failed earlier ones report FAIL individually."""
    results = run_checks(build_checks(app))
    report = format_report(results)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(os.path.join(LOG_DIR, "smoke_report.txt"), "w", encoding="utf-8") as f:
            f.write(report)
    except OSError:
        pass
    return results, report
