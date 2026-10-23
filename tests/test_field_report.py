import os
import sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import field_report as fr  # noqa: E402
import install  # noqa: E402


def test_redact_replaces_home_in_both_slash_styles(monkeypatch):
    monkeypatch.setattr(os.path, "expanduser", lambda p: "C:\\Users\\Jane Doe" if p == "~" else p)
    t = fr.redact("a C:\\Users\\Jane Doe\\x b C:/Users/Jane Doe/y")
    assert "Jane" not in t and t.count("~") == 2


def test_compare_install_detects_missing_changed_and_extra(tmp_path):
    api = tmp_path / "API"
    addin, _ = install.install(str(api))
    assert fr.compare_install(addin) == {"missing": [], "extra": [], "different": [], "total": fr.compare_install(addin)["total"]}
    os.remove(os.path.join(addin, "dfm_engine", "engine.py"))
    with open(os.path.join(addin, "fusion_addin", "extraction.py"), "a") as f:
        f.write("# local edit\n")
    open(os.path.join(addin, "stray.txt"), "w").write("x")
    c = fr.compare_install(addin)
    assert c["missing"] == ["dfm_engine/engine.py"] and c["different"] == ["fusion_addin/extraction.py"] and c["extra"] == ["stray.txt"]


def test_key_lines_and_tail(tmp_path):
    p = tmp_path / "l.log"
    p.write_text("\n".join(["noise"] * 10 + ["2026 INFO button added to panel 'X'", "2026 ERROR boom"]))
    lines = fr.read_tail(str(p), 5)
    assert len(lines) == 5 and fr.key_lines(lines) == ["2026 INFO button added to panel 'X'", "2026 ERROR boom"]
    assert "not found" in fr.read_tail(str(tmp_path / "none.log"))[0]


def test_build_report_sections_and_missing_install(tmp_path, monkeypatch):
    monkeypatch.setattr(fr, "LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setattr(fr, "REPORT_DIR", str(tmp_path / "reports"))
    text = fr.build_report(str(tmp_path / "NoFusion" / "API"))
    for s in ("# Field report", "## Environment", "## Fusion install location", "MISSING", "## Smoke test report",
              "## Log highlights", "## What to fill in by hand", "none (no export has been run)"):
        assert s in text, s


def test_build_report_with_installed_addin_and_logs(tmp_path, monkeypatch):
    api = tmp_path / "API"
    install.install(str(api))
    logs = tmp_path / "logs"; logs.mkdir()
    (logs / "fusion_dfm.log").write_text("x ERROR something failed\ny INFO ok\n")
    (logs / "smoke_report.txt").write_text("OK  fusion_api: Fusion test\n10/10 checks without failure.")
    monkeypatch.setattr(fr, "LOG_DIR", str(logs)); monkeypatch.setattr(fr, "REPORT_DIR", str(tmp_path / "r"))
    text = fr.build_report(str(api))
    assert "files identical" in text and "10/10 checks" in text and "ERROR something failed" in text and "**MISSING**" not in text.split("Add-in folder")[1][:80]


def test_main_writes_file_and_never_commits(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(fr, "LOG_DIR", str(tmp_path / "logs")); monkeypatch.setattr(fr, "REPORT_DIR", str(tmp_path / "r"))
    out = fr.main(["--api-dir", str(tmp_path / "API"), "--out", str(tmp_path / "out" / "r.md")])
    assert os.path.exists(out) and "git add docs/field-reports" in capsys.readouterr().out


def test_tests_never_write_to_the_real_home_logs():
    from fusion_addin import log
    assert log.LOG_DIR != os.path.join(os.path.expanduser("~"), "FusionDFM", "logs") and "fusiondfm_tests_" in log.LOG_DIR
    from fusion_addin import bridge
    assert "fusiondfm_tests_" in bridge.REPORT_DIR


def test_missing_api_dir_message_is_clean(tmp_path, monkeypatch):
    monkeypatch.setattr(fr, "LOG_DIR", str(tmp_path / "l")); monkeypatch.setattr(fr, "REPORT_DIR", str(tmp_path / "r"))
    text = fr.build_report(None)
    assert "**not found**" in text and "Looked for" not in text and "folders: unknown" in text and "folder: ``" not in text


# ---- the three redaction gaps reported in field report 2026-10-23_1214 ---------------------
HOME = "C:\\Users\\Jane Doe"


@pytest.fixture
def fake_home(monkeypatch):
    monkeypatch.setattr(os.path, "expanduser", lambda p: HOME if p == "~" else p)


def test_redact_url_encoded_home_path(fake_home):
    t = fr.redact("creating palette from file:///C:/Users/Jane%20Doe/AppData/Roaming/Autodesk/x/index.html (exists=True)")
    assert "Jane" not in t and "file:///~/AppData/Roaming" in t


def test_redact_python_repr_doubled_backslashes(fake_home):
    line = "report written: {'html': 'C:\\\\Users\\\\Jane Doe\\\\FusionDFM\\\\reports\\\\x.html'}"
    assert "\\\\Users" in line                                   # the literal text has doubled backslashes
    t = fr.redact(line)
    assert "Jane" not in t and "Users" not in t and "'~\\\\FusionDFM" in t


def test_redact_is_case_insensitive_and_covers_both_slash_styles(fake_home):
    t = fr.redact("c:\\users\\jane doe\\a and C:/Users/Jane Doe/b")
    assert "jane" not in t.lower() and t.count("~") == 2


def test_redact_design_name_in_export_file_names_and_logs(fake_home, tmp_path):
    rep = tmp_path / "reports"; rep.mkdir()
    for fn in ("KPRL4FD_Standoff_20261023-121239.html", "KPRL4FD_Standoff_20261023-121239_issues.csv",
               "KPRL4FD_Standoff_20261023-121241-1_comparison.csv"):
        (rep / fn).write_text("x")
    names = fr.private_names(str(rep), "OK active_design: design 'My Secret Part v2'")
    assert set(names) == {"KPRL4FD_Standoff", "My Secret Part v2"}
    text = ("- `KPRL4FD_Standoff_20261023-121239.html` (10 bytes)\n"
            "report written: C:\\\\Users\\\\Jane Doe\\\\FusionDFM\\\\reports\\\\My_Secret_Part_v2_20261023-1212.html\n"
            "design 'My Secret Part v2' and file:///C:/Users/Jane%20Doe/My%20Secret%20Part%20v2.step and KPRL4FD Standoff")
    out = fr.redact(text, names)
    for secret in ("KPRL4FD", "Secret", "Jane", "Doe"):
        assert secret not in out, (secret, out)
    assert "<design>_20261023-121239.html" in out and "~" in out


def test_redact_ignores_short_or_placeholder_names(fake_home):
    assert fr.name_variants("<design>") == [] and fr.name_variants("Box") == []
    assert fr.redact("a Box is a box", ["Box"]) == "a Box is a box"


def test_build_report_redacts_names_from_exports_and_smoke(fake_home, tmp_path, monkeypatch):
    logs = tmp_path / "logs"; logs.mkdir(); rep = tmp_path / "reports"; rep.mkdir()
    (rep / "Gizmo_Bracket_20261023-121239.html").write_text("x")
    (logs / "smoke_report.txt").write_text("OK   active_design: design 'Gizmo Bracket'\n")
    (logs / "fusion_dfm.log").write_text(f"x INFO report written: {{'html': '{HOME}\\\\FusionDFM\\\\reports\\\\Gizmo_Bracket_20261023-121239.html'}}\n")
    monkeypatch.setattr(fr, "LOG_DIR", str(logs)); monkeypatch.setattr(fr, "REPORT_DIR", str(rep))
    text = fr.build_report(None)
    assert "Gizmo" not in text and "Jane" not in text and "<design>" in text
