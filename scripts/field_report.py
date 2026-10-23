#!/usr/bin/env python3
"""Collect everything needed to diagnose a Fusion-DFM first run into ONE markdown file.

  python scripts/field_report.py                 # writes docs/field-reports/<timestamp>.md
  python scripts/field_report.py --run-tests     # also runs the automated tests
  python scripts/field_report.py --api-dir "C:\\Users\\you\\AppData\\Roaming\\Autodesk\\Autodesk Fusion 360\\API"

Nothing is uploaded or committed by this script. Review the file, then commit it yourself (commands are printed).
Home-directory paths (plain, URL-encoded, doubled-backslash) are replaced by '~' and design names (from the smoke report, logs and export file names) by '<design>'.
Still read the file before pushing to a public repo: names this script cannot discover are not removed.
"""
import argparse
import datetime
import hashlib
import os
import platform
import re
import subprocess
import sys
import tempfile
import urllib.parse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import install  # noqa: E402

LOG_DIR = os.environ.get("FUSIONDFM_LOG_DIR") or os.path.join(os.path.expanduser("~"), "FusionDFM", "logs")
REPORT_DIR = os.environ.get("FUSIONDFM_REPORT_DIR") or os.path.join(os.path.expanduser("~"), "FusionDFM", "reports")
KEY_MARKERS = ("ERROR", "Traceback", "WARNING", "starting", "stopping", "toolbar panels", "button added", "creating palette",
               "palette page loaded", "extracted:", "extract_all", "analysis ", "comparison", "report written", "ignored inner loop",
               "thickness:", "face census")


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_")


def home_variants(home: str) -> list:
    """Every spelling of the home directory that shows up in logs: native, both slash styles, Python-repr doubled
    backslashes, and URL-encoded (file:///C:/Users/First%20Last/...)."""
    fwd, back = home.replace("\\", "/"), home.replace("/", "\\")
    v = {home, fwd, back, back.replace("\\", "\\\\"), urllib.parse.quote(fwd, safe="/:"), urllib.parse.quote(back, safe="\\:")}
    return sorted((x for x in v if x and x != "~"), key=len, reverse=True)


def name_variants(name: str) -> list:
    """Design/document name as it appears raw, with underscores (export file names), URL-encoded, and slugged."""
    name = name.strip()
    if len(name) < 4 or name.startswith("<"):
        return []
    v = {name, name.replace(" ", "_"), _slug(name), urllib.parse.quote(name), name.replace("_", " ")}
    return sorted((x for x in v if len(x) >= 4), key=len, reverse=True)


EXPORT_NAME = re.compile(r"^(.+?)_\d{8}-\d{6}(?:-\d+)?(?:_issues|_comparison)?\.(?:html|csv)$")


def private_names(report_dir: str, *texts: str) -> list:
    """Design names: from "design '<name>'" in smoke/log text and from <Name>_<timestamp>.html export file names."""
    names = set()
    for t in texts:
        names.update(re.findall(r"design '([^']+)'", t))
    if os.path.isdir(report_dir):
        for fn in os.listdir(report_dir):
            m = EXPORT_NAME.match(fn)
            if m:
                names.add(m.group(1))
    return sorted(n for n in names if name_variants(n))


def redact(text: str, names=()) -> str:
    """Replace design names with <design> and the home directory (all spellings, any case) with ~."""
    for n in sorted(names, key=len, reverse=True):
        for v in name_variants(n):
            text = re.sub(re.escape(v), "<design>", text, flags=re.I)
    for v in home_variants(os.path.expanduser("~")):
        text = re.sub(re.escape(v), "~", text, flags=re.I)
    return text


def sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()[:12]


def tree_hashes(root: str) -> dict:
    out = {}
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x != "__pycache__"]
        for fn in files:
            if fn.endswith(".pyc"):
                continue
            p = os.path.join(d, fn)
            out[os.path.relpath(p, root).replace("\\", "/")] = sha(p)
    return out


def compare_install(installed: str) -> dict:
    """Compare the installed add-in folder with a fresh bundle built from this repo."""
    with tempfile.TemporaryDirectory() as tmp:
        expected = tree_hashes(install.build_addin(tmp))
    actual = tree_hashes(installed) if os.path.isdir(installed) else {}
    return {"missing": sorted(set(expected) - set(actual)), "extra": sorted(set(actual) - set(expected)),
            "different": sorted(k for k in expected if k in actual and expected[k] != actual[k]), "total": len(expected)}


def read_tail(path: str, n: int = 150) -> list:
    if not os.path.exists(path):
        return [f"(not found: {path})"]
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read().splitlines()[-n:]


def key_lines(lines: list) -> list:
    return [ln for ln in lines if any(m in ln for m in KEY_MARKERS)]


def git(*args):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=20).stdout.strip()
    except Exception as e:  # git missing is fine
        return f"(git unavailable: {e})"


def build_report(api_dir, run_tests=False, tail=150) -> str:
    now = datetime.datetime.now().astimezone()
    o = [f"# Field report {now:%Y-%m-%d %H:%M %Z}", ""]
    o += ["## Environment", f"- OS: {platform.platform()}", f"- Python (this script): {platform.python_version()}",
          f"- Repo branch: {git('rev-parse', '--abbrev-ref', 'HEAD')}", f"- Repo commit: {git('rev-parse', '--short', 'HEAD')}",
          f"- Uncommitted changes: {'yes' if git('status', '--porcelain') else 'no'}", ""]
    o.append("## Fusion install location")
    cands = ', '.join('`%s`' % c + (' [exists]' if os.path.isdir(c) else '') for c in install.candidate_api_dirs())
    o.append(f"- API folder used: {'`' + api_dir + '`' if api_dir else '**not found** — pass --api-dir'}  (candidates: {cands})")
    addin = os.path.join(api_dir or "", "AddIns", install.ADDIN) if api_dir else ""
    smoke = os.path.join(api_dir or "", "Scripts", install.SMOKE) if api_dir else ""
    if api_dir:
        o.append(f"- Add-in folder: `{addin}` — {'present' if os.path.isdir(addin) else '**MISSING**'}")
        o.append(f"- Smoke script folder: `{smoke}` — {'present' if os.path.isdir(smoke) else '**MISSING** (manual installs must copy smoke_test/)'}")
    else:
        o.append("- Add-in / smoke script folders: unknown (API folder not found)")
    if addin and os.path.isdir(addin):
        c = compare_install(addin)
        o.append(f"- Installed vs this repo: {c['total'] - len(c['missing']) - len(c['different'])}/{c['total']} files identical; "
                 f"missing {len(c['missing'])}, different {len(c['different'])}, extra {len(c['extra'])}")
        for label in ("missing", "different", "extra"):
            for f in c[label][:20]:
                o.append(f"  - {label}: `{f}`")
    o.append("")
    o.append("## Smoke test report (`smoke_report.txt`)")
    sr = os.path.join(LOG_DIR, "smoke_report.txt")
    o.append("```\n" + ("\n".join(read_tail(sr, 60))) + "\n```")
    o.append("")
    lines = read_tail(os.path.join(LOG_DIR, "fusion_dfm.log"), tail)
    o.append(f"## Log highlights (`fusion_dfm.log`, last {tail} lines filtered)")
    o.append("```\n" + "\n".join(key_lines(lines)[-80:]) + "\n```")
    o.append("<details><summary>Full log tail</summary>\n\n```\n" + "\n".join(lines) + "\n```\n</details>\n")
    o.append("## Recent exported reports")
    if os.path.isdir(REPORT_DIR):
        fs = sorted(os.listdir(REPORT_DIR))[-6:]
        o += [f"- `{f}` ({os.path.getsize(os.path.join(REPORT_DIR, f))} bytes)" for f in fs] or ["- none"]
    else:
        o.append("- none (no export has been run)")
    o.append("")
    if run_tests:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider"], cwd=ROOT,
                           capture_output=True, text=True, timeout=600)
        o += ["## Automated tests", "```\n" + (r.stdout + r.stderr)[-3000:] + "\n```", ""]
    o += ["## What to fill in by hand", "- What you did (steps) and what you expected:", "- What happened instead (screenshots welcome):",
          "- Part under test (material, thickness, features):", ""]
    smoke_text = "\n".join(read_tail(sr, 60))
    names = private_names(REPORT_DIR, smoke_text, "\n".join(lines))
    return redact("\n".join(o), names)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api-dir")
    ap.add_argument("--run-tests", action="store_true")
    ap.add_argument("--out", help="output file (default docs/field-reports/<timestamp>.md)")
    a = ap.parse_args(argv)
    try:
        api = a.api_dir or install.pick_api_dir()
    except SystemExit:
        api = None
    text = build_report(api, a.run_tests)
    out = a.out or os.path.join(ROOT, "docs", "field-reports", datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S") + ".md")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"Wrote {out}\nReview it, then:\n  git add docs/field-reports && git commit -m \"Field report\" && git push")
    return out


if __name__ == "__main__":
    main()
