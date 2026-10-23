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
