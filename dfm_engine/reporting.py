"""Exportable reports (self-contained HTML, CSV). Pure Python, no external services or assets."""
from __future__ import annotations
import csv
import datetime as _dt
import html
import io
import os
import re
from . import __version__
from .units import fmt_len

VERDICT_LABEL = {"COMPATIBLE": "Compatible", "CONDITIONALLY_COMPATIBLE": "Conditionally compatible",
                 "NEEDS_REVIEW": "Needs review", "INCOMPATIBLE": "Incompatible"}
LIMITATIONS = [
    "This report is generated automatically. It is decision support, not a manufacturer quote or approval; confirm with the manufacturer before ordering.",
    "Rules marked non-blocking (warnings) never make a part incompatible, but they are always listed and prevent an unconditional 'compatible' verdict. Only rules that are enabled AND verified against an official source decide PASS/FAIL. Unverified or disabled rules are listed as 'not checked' and never count as passes.",
    "Anything that could not be measured or classified is reported as NEEDS REVIEW. A missing value is never treated as a pass.",
    "Manufacturer requirements change. Each rule shows its source and the date it was verified; re-verify before relying on a value.",
    "Geometry is extracted from the Fusion model: only circular through holes, slots, rectangular cutouts and irregular outlines are recognised; irregular cutout widths are not computed.",
    "Flat size comes from the axis-aligned bounding box of the flat pattern and can overstate a rotated pattern. Flange lengths are reported from the bend apex where a manufacturer defines them that way.",
    "Conflicting values published by a manufacturer are reported as NEEDS REVIEW rather than resolved by this tool.",
]


def _now():
    return _dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")


def build_context(comparison: dict, parts: list, model_name: str = "", document: str = "", generated: str = "") -> dict:
    """comparison: Comparison.to_dict(); parts: list of bridge.part_summary dicts."""
    return {"title": f"Manufacturability report - {model_name or (parts[0]['name'] if parts else 'model')}",
            "model_name": model_name, "document": document, "generated": generated or _now(), "tool_version": __version__,
            "parts": parts, "comparison": comparison, "limitations": LIMITATIONS}


def _e(x):
    return html.escape("" if x is None else str(x))


def _slug(s):
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_") or "report"


CSS = """
:root{--fg:#1f2933;--mut:#5f6b7a;--bd:#d9dee4;--bg:#fff;--fail:#b71c1c;--warn:#8a5a00;--pass:#2e7d32;--info:#1565c0;--acc:#0b6bcb}
*{box-sizing:border-box}body{font:14px/1.5 system-ui,Segoe UI,Arial,sans-serif;color:var(--fg);background:var(--bg);margin:0;padding:24px;max-width:1000px;margin:auto}
h1{font-size:22px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 8px;border-bottom:2px solid var(--bd);padding-bottom:4px}h3{font-size:14px;margin:16px 0 6px}
.meta{color:var(--mut);font-size:12px}table{border-collapse:collapse;width:100%;margin:8px 0}th,td{border:1px solid var(--bd);padding:5px 8px;text-align:left;vertical-align:top;font-size:13px}
th{background:#f3f5f7}.tag{display:inline-block;font-size:11px;font-weight:700;padding:1px 8px;border-radius:10px;border:1px solid currentColor;white-space:nowrap}
.COMPATIBLE,.PASS{color:var(--pass)}.CONDITIONALLY_COMPATIBLE,.NEEDS_REVIEW{color:var(--warn)}.INCOMPATIBLE,.FAIL{color:var(--fail)}.SKIPPED{color:var(--mut)}.WARNING{color:var(--warn)}.box.WARNING{border-left-color:var(--warn)}
.box{border:1px solid var(--bd);border-left:4px solid var(--mut);border-radius:4px;padding:8px 12px;margin:8px 0}.box.FAIL{border-left-color:var(--fail)}.box.NEEDS_REVIEW{border-left-color:var(--warn)}
.demo{background:#fff3cd;border:1px solid #e0c36a;padding:8px 12px;border-radius:4px;font-weight:600;margin:8px 0}.disc{background:#f6f8fa;border:1px solid var(--bd);border-radius:4px;padding:8px 14px}
.fix{margin-top:4px}.src{color:var(--mut);font-size:12px}details{margin:6px 0}summary{cursor:pointer;color:var(--mut)}a{color:var(--acc)}
@media print{body{padding:0}details{display:block}details>*{display:block}}
"""


def _issue_html(r):
    parts = [f'<div class="box {r["status"]}"><span class="tag {r["status"]}">{r["status"].replace("_", " ")}</span> '
             f'<b>{_e(r.get("title") or r.get("ref_label") or r["rule_type"].replace("_", " "))}</b>'
             f'{" <span class=src>[advisory]</span>" if r.get("strength") == "advisory" else ""}<div>{_e(r["explanation"])}</div>']
    if r["status"] in ("FAIL", "NEEDS_REVIEW", "WARNING") and r.get("recommendation"):
        parts.append(f'<div class="fix"><b>{"Fix" if r["status"] == "FAIL" else ("Suggested fix" if r["status"] == "WARNING" else "Next step")}:</b> {_e(r["recommendation"])}</div>')
    if r.get("rationale") and r["status"] == "FAIL":
        parts.append(f'<div class="src"><b>Why:</b> {_e(r["rationale"])}</div>')
    for c in r.get("corrections", []):
        parts.append(f'<div class="src"><b>Proposed correction ({_e(c["kind"])}, {_e(c["confidence"])}):</b> {_e(c["summary"])}'
                     f'{"; side effects: " + _e("; ".join(c["side_effects"])) if c.get("side_effects") else ""}</div>')
    src = (f'<a href="{_e(r["source_url"])}">source</a> (verified {_e(r["date_verified"])})' if r.get("source_url") else
           ("demo rule - not a real manufacturer requirement" if r.get("demo") else "no source"))
    parts.append(f'<div class="src">{_e(r["rule_id"])} · {src}{" · " + _e(r["notes"]) if r.get("notes") else ""}</div></div>')
    return "".join(parts)


def render_html(ctx: dict) -> str:
    comp = ctx["comparison"]
    entries = comp["entries"]
    o = [f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{_e(ctx["title"])}</title><style>{CSS}</style></head><body>']
    o.append(f'<h1>{_e(ctx["title"])}</h1><div class="meta">Analysis date: {_e(ctx["generated"])} · Fusion-DFM {_e(ctx["tool_version"])}'
             f'{" · Document: " + _e(ctx["document"]) if ctx.get("document") else ""}</div>')
    if any(e["demo"] for e in entries):
        o.append('<div class="demo">Contains results from the DEMONSTRATION profile: fictional limits, not a real manufacturer.</div>')
    # --- comparison table
    o.append("<h2>Manufacturer comparison</h2><table><tr><th>Manufacturer</th><th>Verdict</th><th>Confirmed failures</th><th>Warnings</th><th>Unresolved checks</th><th>Passed</th><th>Not checked</th><th>Notes</th></tr>")
    for e in entries:
        notes = e["verdict_text"]
        if e["coverage_gap_labels"]:
            notes += " Unverified: " + ", ".join(e["coverage_gap_labels"]) + "."
        if e["demo"]:
            notes = "DEMO profile. " + notes
        o.append(f'<tr><td><b>{_e(e["manufacturer_name"])}</b><div class="src">{_e(e["process_id"])} · profile {_e(e["profile_status"])}</div></td>'
                 f'<td><span class="tag {e["verdict"]}">{VERDICT_LABEL[e["verdict"]]}</span></td><td>{e["failures"]}</td><td>{e["warnings"]}</td><td>{e["unresolved"]}</td>'
                 f'<td>{e["passed"]}</td><td>{e["not_checked"]}</td><td>{_e(notes)}</td></tr>')
    o.append("</table>")
    # --- model info
    o.append("<h2>Model information</h2><table><tr><th>Part</th><th>Material</th><th>Thickness</th><th>Flat size</th><th>Features</th><th>Instances</th><th>Not extractable</th></tr>")
    for p in ctx["parts"]:
        flat = " x ".join(f"{x:.1f}" for x in p["flat_dimensions_mm"]) + " mm" if p.get("flat_dimensions_mm") else "unsupported"
        c = p["counts"]
        o.append(f'<tr><td>{_e(p["name"])}<div class="src">{_e(p.get("component_path", ""))}</div></td><td>{_e(p.get("material") or "unknown")}</td>'
                 f'<td>{_e(fmt_len(p["thickness_mm"]) if p.get("thickness_mm") else "unknown")}<div class="src">{_e(p.get("thickness_source", ""))}</div></td>'
                 f'<td>{_e(flat)}</td><td>{c["holes"]} holes, {c.get("cutouts", 0)} cutouts, {c["bends"]} bends, {c["flanges"]} flanges</td>'
                 f'<td>{p.get("instance_count", 1)}</td><td>{_e("; ".join(f"{k}: {v}" for k, v in p["unsupported"].items()) or "-")}</td></tr>')
    o.append("</table>")
    warns = sorted({w for p in ctx["parts"] for w in p.get("warnings", [])})
    if warns:
        o.append("<h3>Extraction warnings</h3><ul>" + "".join(f"<li>{_e(w)}</li>" for w in warns) + "</ul>")
    # --- per manufacturer details
    for e in entries:
        o.append(f'<h2>{_e(e["manufacturer_name"])} - {VERDICT_LABEL[e["verdict"]]}</h2><div class="meta">{_e(e["summary"])}</div>')
        if e["research_status"] in ("blocked", "not_started", "partial") and e["research_notes"]:
            o.append(f'<div class="disc"><b>Data status ({_e(e["research_status"])}):</b> {_e(e["research_notes"])}</div>')
        for rep in e["reports"]:
            fails = [r for r in rep["results"] if r["status"] == "FAIL"]
            warns = [r for r in rep["results"] if r["status"] == "WARNING"]
            nrs = [r for r in rep["results"] if r["status"] == "NEEDS_REVIEW"]
            oks = [r for r in rep["results"] if r["status"] == "PASS"]
            sk = [r for r in rep["results"] if r["status"] == "SKIPPED"]
            o.append(f'<h3>{_e(rep["part_name"])} <span class="src">material: {_e(rep.get("material_name") or "not matched")}'
                     f'{" · " + _e(rep["thickness_match"]) if rep.get("thickness_match") else ""}</span></h3>')
            for n in rep["notes"]:
                o.append(f'<div class="src">{_e(n)}</div>')
            if fails:
                o.append(f"<b>Confirmed failures ({len(fails)})</b>" + "".join(_issue_html(r) for r in fails))
            if warns:
                o.append(f"<b>Warnings - non-blocking ({len(warns)})</b>" + "".join(_issue_html(r) for r in warns))
            if nrs:
                o.append(f"<b>Needs review ({len(nrs)})</b>" + "".join(_issue_html(r) for r in nrs))
            if oks:
                o.append(f"<details><summary>Passed checks ({len(oks)})</summary>" + "".join(_issue_html(r) for r in oks) + "</details>")
            if sk:
                o.append(f"<details><summary>Rules not checked - no verified data ({len(sk)})</summary>" + "".join(_issue_html(r) for r in sk) + "</details>")
            if not (fails or nrs or oks or sk):
                o.append("<div class='src'>No rules applied.</div>")
    # --- sources
    srcs = {}
    for e in entries:
        for rep in e["reports"]:
            for r in rep["results"]:
                if r.get("source_url"):
                    srcs.setdefault((e["manufacturer_name"], r["source_url"]), r["date_verified"])
    o.append("<h2>Sources</h2>")
    if srcs:
        o.append("<table><tr><th>Manufacturer</th><th>Source</th><th>Verified</th></tr>" + "".join(
            f'<tr><td>{_e(m)}</td><td><a href="{_e(u)}">{_e(u)}</a></td><td>{_e(d)}</td></tr>' for (m, u), d in sorted(srcs.items())) + "</table>")
    else:
        o.append("<div class='src'>No verified manufacturer source was used by any evaluated rule.</div>")
    o.append('<h2>Limitations and disclosures</h2><div class="disc"><ul>' + "".join(f"<li>{_e(x)}</li>" for x in ctx["limitations"]) + "</ul></div>")
    o.append("</body></html>")
    return "".join(o)


ISSUE_COLS = ["manufacturer", "process", "part", "rule_id", "title", "status", "severity", "strength", "feature", "measured", "required",
              "explanation", "recommendation", "proposed_correction", "source_url", "date_verified", "demo_profile"]


def render_issues_csv(ctx: dict, include_passes: bool = False) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(ISSUE_COLS)
    for e in ctx["comparison"]["entries"]:
        for rep in e["reports"]:
            for r in rep["results"]:
                if r["status"] == "PASS" and not include_passes:
                    continue
                m = "" if r.get("measured") is None else f'{r["measured"]:.4g}'
                w.writerow([e["manufacturer_name"], e["process_id"], rep["part_name"], r["rule_id"], r.get("title", ""), r["status"], r["severity"],
                            r.get("strength", ""), r.get("ref_label") or r.get("feature_kind", ""), m, r.get("required") or "",
                            r["explanation"], r.get("recommendation", ""), "; ".join(c["summary"] for c in r.get("corrections", [])),
                            r.get("source_url", ""), r.get("date_verified", ""), "yes" if r.get("demo") else ""])
    return buf.getvalue()


def render_comparison_csv(ctx: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["manufacturer", "process", "verdict", "confirmed_failures", "warnings", "unresolved_checks", "passed", "not_checked",
                "unverified_categories", "reasons", "suggested_corrections", "profile_status", "demo_profile"])
    for e in ctx["comparison"]["entries"]:
        w.writerow([e["manufacturer_name"], e["process_id"], e["verdict"], e["failures"], e["warnings"], e["unresolved"], e["passed"], e["not_checked"],
                    "; ".join(e["coverage_gap_labels"]), " | ".join(r["explanation"] for r in e["reasons"] + e["warning_items"]),
                    " | ".join(c["summary"] for c in e["corrections"]), e["profile_status"], "yes" if e["demo"] else ""])
    return buf.getvalue()


def write_reports(ctx: dict, directory: str, basename: str = "") -> dict:
    """Write HTML + issues CSV + comparison CSV. Returns {kind: path}. Never overwrites: adds a numeric suffix."""
    os.makedirs(directory, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = _slug(basename or ctx.get("model_name") or "report") + "_" + stamp
    out = {}
    for kind, ext, text in (("html", ".html", render_html(ctx)), ("issues_csv", "_issues.csv", render_issues_csv(ctx, True)),
                            ("comparison_csv", "_comparison.csv", render_comparison_csv(ctx))):
        path, n = os.path.join(directory, base + ext), 1
        while os.path.exists(path):
            path = os.path.join(directory, f"{base}-{n}{ext}")
            n += 1
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        out[kind] = path
    return out
