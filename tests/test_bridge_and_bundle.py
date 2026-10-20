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


def test_install_bundle_layout(tmp_path):
    sys.path.insert(0, os.path.join(ROOT, "scripts"))
    import install
    dest = install.build(str(tmp_path))
    for f in ("FusionDFM.py", "FusionDFM.manifest", "fusion_addin/app_main.py", "fusion_addin/ui/index.html",
              "dfm_engine/engine.py", "manufacturers/sendcutsend.json"):
        assert os.path.exists(os.path.join(dest, f)), f
    json.load(open(os.path.join(dest, "FusionDFM.manifest")))
    # bundle's engine finds the bundled manufacturers
    code = "from dfm_engine import list_profiles; p,e=list_profiles(); assert len(p)==4 and not e"
    subprocess.run([sys.executable, "-c", code], cwd=dest, check=True)


def test_fusion_modules_compile():
    import py_compile
    for f in ("app_main", "extraction", "highlight", "FusionDFM"):
        py_compile.compile(os.path.join(ROOT, "fusion_addin", f + ".py"), doraise=True)
