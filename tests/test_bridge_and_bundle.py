import json, os, subprocess, sys, types
from dfm_engine import PartModel, Hole, Bend, Flange, GeometryRef
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_profiles_payload_and_results_json_serialisable():
    from fusion_addin import bridge
    pp = bridge.profiles_payload()
    assert pp["errors"] == [] and {p["id"] for p in pp["profiles"]} >= {"demo", "sendcutsend"}
    part = PartModel("p", thickness_mm=1.5, material_name="steel", flat_dimensions_mm=(100, 50),
                     bends=[Bend(0.2, ref=GeometryRef("bend", "tok", "Bend 1"))],
                     holes=[Hole(5, dist_to_edge_mm=10)], unsupported={"x": "y"})
    d = bridge.results_payload(part, ["w"], {"manufacturer_id": "demo", "process_id": "sheet_metal_bending"})
    json.dumps(d)
    assert d["overall"] == "FAIL" and d["demo"]
    assert any(r["token"] == "tok" for r in d["results"])


def test_unknown_manufacturer_rejected():
    import pytest
    from fusion_addin import bridge
    with pytest.raises(ValueError):
        bridge.results_payload(PartModel("p"), [], {"manufacturer_id": "nope", "process_id": "x"})


def test_engine_does_not_import_cad():
    code = "import sys; import dfm_engine; assert not any(m.startswith('adsk') for m in sys.modules)"
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)


def test_install_layout(tmp_path):
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import install
    api = tmp_path / "Autodesk Fusion" / "API"
    addin, smoke = install.install(str(api))
    assert addin == str(api / "AddIns" / "FusionDFM") and smoke == str(api / "Scripts" / "FusionDFMSmoke")
    for f in ("FusionDFM.py", "FusionDFM.manifest", "fusion_addin/app_main.py", "fusion_addin/smoke.py",
              "fusion_addin/ui/index.html", "dfm_engine/engine.py", "manufacturers/sendcutsend.json"):
        assert os.path.exists(os.path.join(addin, f)), f
    assert not os.path.exists(os.path.join(addin, "fusion_addin", "FusionDFM.py"))  # moved to root
    for d, n in ((addin, "FusionDFM"), (smoke, "FusionDFMSmoke")):
        m = json.load(open(os.path.join(d, n + ".manifest")))
        assert os.path.exists(os.path.join(d, n + ".py")) and m["type"] in ("addin", "script")
    code = "from dfm_engine import list_profiles; p,e=list_profiles(); assert len(p)==4 and not e"
    subprocess.run([sys.executable, "-c", code], cwd=addin, check=True)
    install.install(str(api))  # re-install over an existing copy works


def test_missing_api_dir_gives_clear_error(monkeypatch):
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import install
    monkeypatch.setattr(install, "candidate_api_dirs", lambda: ["/nonexistent/a", "/nonexistent/b"])
    import pytest
    with pytest.raises(SystemExit, match="Could not find the Fusion API folder"):
        install.pick_api_dir()


def test_fusion_modules_compile():
    import py_compile
    for f in ("app_main", "extraction", "highlight", "smoke", "FusionDFM"):
        py_compile.compile(os.path.join(ROOT, "fusion_addin", f + ".py"), doraise=True)
    py_compile.compile(os.path.join(ROOT, "smoke_test", "FusionDFMSmoke.py"), doraise=True)


def test_export_guard_returns_existing_files_for_the_same_analysis():
    from fusion_addin.bridge import ExportGuard
    g = ExportGuard()
    assert g.lookup(1) is None and g.lookup(None) is None
    g.record(1, {"html": "a.html"})
    assert g.lookup(1) == {"html": "a.html"}          # double click on the same analysis: no second file
    assert g.lookup(2) is None                        # a new analysis may be exported again
    g.record(2, {"html": "b.html"})
    assert g.lookup(1) is None and g.lookup(2) == {"html": "b.html"}


def test_app_main_wires_the_guard_and_stamps_every_analysis():
    src = open(os.path.join(ROOT, "fusion_addin", "app_main.py")).read()
    assert src.count("_bump()") >= 3 and "_guard.lookup(_stamp)" in src and "_guard.record(_stamp" in src
