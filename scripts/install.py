#!/usr/bin/env python3
"""Assemble the add-in bundle (+ smoke-test script) and copy it into Fusion's folders.

  python scripts/install.py              # install into %APPDATA%\\Autodesk\\Autodesk Fusion\\API (Windows)
  python scripts/install.py --api-dir D  # use D as the ...\\API folder (contains AddIns and Scripts)
  python scripts/install.py --dry-run    # print what would happen
"""
import argparse
import os
import platform
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDIN, SMOKE = "FusionDFM", "FusionDFMSmoke"


def candidate_api_dirs():
    """Autodesk docs: %appdata%\\Autodesk\\Autodesk Fusion\\API (older installs used 'Autodesk Fusion 360')."""
    if platform.system() == "Windows":
        base = os.path.join(os.environ.get("APPDATA", ""), "Autodesk")
    else:
        base = os.path.expanduser("~/Library/Application Support/Autodesk")
    return [os.path.join(base, "Autodesk Fusion", "API"), os.path.join(base, "Autodesk Fusion 360", "API")]


def pick_api_dir():
    c = candidate_api_dirs()
    existing = [p for p in c if os.path.isdir(p)]
    if existing:
        return existing[0]
    raise SystemExit("Could not find the Fusion API folder. Looked for:\n  " + "\n  ".join(c) +
                     "\nStart Fusion once (it creates the folder) or pass --api-dir <path>.")


def build_addin(addins_dir):
    dest = os.path.join(addins_dir, ADDIN)
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    ign = shutil.ignore_patterns("__pycache__", "*.pyc")
    for pkg in ("fusion_addin", "dfm_engine", "manufacturers"):
        shutil.copytree(os.path.join(ROOT, pkg), os.path.join(dest, pkg), ignore=ign)
    # Fusion needs <folder>/<folder>.py and <folder>.manifest at the add-in root
    for f in ("FusionDFM.py", "FusionDFM.manifest"):
        shutil.move(os.path.join(dest, "fusion_addin", f), os.path.join(dest, f))
    return dest


def build_smoke(scripts_dir):
    dest = os.path.join(scripts_dir, SMOKE)
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    shutil.copytree(os.path.join(ROOT, "smoke_test"), dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return dest


def install(api_dir):
    addins, scripts = os.path.join(api_dir, "AddIns"), os.path.join(api_dir, "Scripts")
    os.makedirs(addins, exist_ok=True)
    os.makedirs(scripts, exist_ok=True)
    return build_addin(addins), build_smoke(scripts)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-dir", help="the Fusion ...\\API folder (default: auto-detect)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    api = a.api_dir or pick_api_dir()
    if a.dry_run:
        print(f"Would install add-in to {os.path.join(api, 'AddIns', ADDIN)}\n"
              f"and smoke script to {os.path.join(api, 'Scripts', SMOKE)}")
        sys.exit(0)
    ad, sm = install(api)
    print(f"Installed add-in: {ad}\nInstalled smoke test script: {sm}\n"
          "Next: in Fusion press Shift+S (Scripts and Add-Ins) > Add-Ins tab > FusionDFM > Run.")
