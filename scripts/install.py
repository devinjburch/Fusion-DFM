#!/usr/bin/env python3
"""Assemble the add-in bundle and copy it into Fusion's AddIns folder.

  python scripts/install.py            # install (copy)
  python scripts/install.py --dest DIR # build bundle into DIR/FusionDFM (any folder; for inspection)
"""
import argparse
import os
import platform
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "FusionDFM"


def addins_dir():
    if platform.system() == "Windows":
        return os.path.join(os.environ["APPDATA"], "Autodesk", "Autodesk Fusion 360", "API", "AddIns")
    return os.path.expanduser("~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns")


def build(dest_parent):
    dest = os.path.join(dest_parent, NAME)
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    ign = shutil.ignore_patterns("__pycache__", "*.pyc")
    for pkg in ("fusion_addin", "dfm_engine", "manufacturers"):
        shutil.copytree(os.path.join(ROOT, pkg), os.path.join(dest, pkg), ignore=ign)
    # Fusion requires <folder>/<folder>.py and <folder>.manifest at the add-in root
    shutil.move(os.path.join(dest, "fusion_addin", "FusionDFM.py"), os.path.join(dest, "FusionDFM.py"))
    shutil.move(os.path.join(dest, "fusion_addin", "FusionDFM.manifest"), os.path.join(dest, "FusionDFM.manifest"))
    return dest


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", help="parent folder for the bundle (default: Fusion AddIns folder)")
    a = ap.parse_args()
    out = build(a.dest or addins_dir())
    print(f"Installed to {out}\nIn Fusion: Utilities > Add-Ins > Scripts and Add-Ins > Add-Ins tab > FusionDFM > Run.")
