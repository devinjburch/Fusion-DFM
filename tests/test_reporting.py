import csv
import io
import os
import re
from dfm_engine import PartModel, Hole, Bend, Flange, list_profiles
from dfm_engine.compare import compare
from dfm_engine.reporting import build_context, render_html, render_issues_csv, render_comparison_csv, write_reports, ISSUE_COLS
from fusion_addin import bridge

IN = 25.4
PROFILES, _ = list_profiles()


def part(**kw):
    d = dict(name="Bracket <1>", thickness_mm=0.119 * IN, material_name="Mild Steel", flat_dimensions_mm=(300, 100),
             bends=[Bend(inner_radius_mm=0.2 * IN, angle_deg=90, length_mm=100)],
             flanges=[Flange(length_mm=5, length_apex_mm=0.2 * IN, bend_angle_deg=90)],
             holes=[Hole(diameter_mm=6, dist_to_edge_mm=20, dist_to_bend_mm=30, has_adjacent_bend=True, bend_zone_max_mm=6)],
             unsupported={"slots_and_cutouts": "n/a"})
    d.update(kw)
    return PartModel(**d)


def ctx(**kw):
    p = part(**kw)
    c = compare(p, PROFILES)
    return build_context(c.to_dict(), [bridge.part_summary(p, ["a warning <b>"])], "Bracket <1>", "Doc & Co", "2026-10-21 10:00 UTC")


def test_html_report_is_self_contained_and_escaped():
    h = render_html(ctx())
    assert h.startswith("<!doctype html>") and "<script" not in h and "http://" not in h.replace("https://", "")
    assert "Bracket &lt;1&gt;" in h and "Bracket <1>" not in h and "&lt;b&gt;" in h      # user text escaped
    assert "Doc &amp; Co" in h and "2026-10-21 10:00 UTC" in h and "Fusion-DFM 0.2.0" in h


def test_html_contains_required_sections_and_disclosures():
    h = render_html(ctx())
    for s in ("Manufacturer comparison", "Model information", "Sources", "Limitations and disclosures",
              "SendCutSend", "PCBWay", "Xometry", "Confirmed failures", "Proposed correction", "Rules not checked",
              "never treated as a pass", "A missing value is never treated as a pass"):
        assert s in h or s.lower() in h.lower(), s
    assert "https://sendcutsend.com/bending-calculator/" in h and "verified 2026-10-20" in h
    assert "blocked" in h and "Data status" in h          # unverified manufacturers explain why


def test_html_marks_demo_and_unconditional_verdicts_never_for_unverified():
    h = render_html(ctx())
    assert "DEMONSTRATION profile" in h
    row = re.search(r"<b>PCBWay</b>.*?</tr>", h, re.S).group(0)
    assert "Needs review" in row and "Compatible</span>" not in row


def test_issues_csv_columns_rows_and_roundtrip():
    c = ctx()
    text = render_issues_csv(c, include_passes=False)
    rows = list(csv.DictReader(io.StringIO(text)))
    assert list(rows[0].keys()) == ISSUE_COLS
    assert rows and all(r["status"] != "PASS" for r in rows)
    fl = next(r for r in rows if r["rule_id"] == "scs.min_flange_length")
    assert fl["status"] == "FAIL" and "0.466 in" in fl["explanation"] and fl["source_url"].startswith("https://")
    assert "increase" in fl["proposed_correction"]
    full = list(csv.DictReader(io.StringIO(render_issues_csv(c, include_passes=True))))
    assert len(full) > len(rows) and any(r["status"] == "PASS" for r in full)


def test_comparison_csv():
    rows = list(csv.DictReader(io.StringIO(render_comparison_csv(ctx()))))
    by = {r["manufacturer"]: r for r in rows}
    assert by["SendCutSend"]["verdict"] == "INCOMPATIBLE" and by["PCBWay"]["verdict"] == "NEEDS_REVIEW"
    assert by["DEMO Manufacturer (fictional)"]["demo_profile"] == "yes"


def test_write_reports_never_overwrites(tmp_path):
    c = ctx()
    a = write_reports(c, str(tmp_path / "out"), "My Part/1")
    b = write_reports(c, str(tmp_path / "out"), "My Part/1")
    assert set(a) == {"html", "issues_csv", "comparison_csv"}
    assert all(os.path.exists(p) for p in list(a.values()) + list(b.values()))
    assert len(set(a.values()) | set(b.values())) == 6 and "/" not in os.path.basename(a["html"])
