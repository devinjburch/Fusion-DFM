"""Manufacturer database integrity: every number traceable, nothing unverified can decide PASS/FAIL."""
import copy
import json
import os
import re
import pytest
from dfm_engine import list_profiles, load_profile_dict, ProfileError
from dfm_engine.profile import DEFAULT_DIR
from dfm_engine.units import in_to_mm, mm_to_in, fmt_len

PROFILES, ERRORS = list_profiles()
BY_ID = {p["manufacturer"]["id"]: p for p in PROFILES}
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REAL = [p for p in PROFILES if p["profile_status"] != "demo"]


def test_all_profiles_load():
    assert ERRORS == [] and set(BY_ID) == {"sendcutsend", "pcbway", "xometry", "demo"}


def test_no_profile_scope_conflicts():
    for p in PROFILES:
        assert p["_warnings"] == [], p["manufacturer"]["id"]


@pytest.mark.parametrize("p", REAL, ids=lambda p: p["manufacturer"]["id"])
def test_real_profiles_every_enabled_rule_is_verified_and_sourced(p):
    for proc in p["processes"]:
        for r in proc["rules"]:
            if r["enabled"]:
                assert r["verified"], r["id"]
                assert r["source"]["url"].startswith("https://") and DATE.match(r["source"]["date_verified"]), r["id"]
            else:
                assert r["limitations"], f"{r['id']}: disabled rule must explain why"


@pytest.mark.parametrize("p", REAL, ids=lambda p: p["manufacturer"]["id"])
def test_real_profiles_tables_tolerances_restrictions_are_sourced(p):
    for proc in p["processes"]:
        for m in proc["materials"]:
            for row in m.get("thickness_specs", []):
                assert row["source"]["url"].startswith("https://") and DATE.match(row["source"]["date_verified"])
                for cands in (row.get("conflicts") or {}).values():
                    assert all(c["source"]["url"] for c in cands)
        for t in proc.get("tolerances", []) + proc.get("restrictions", []):
            assert t["source"]["url"].startswith("https://") and DATE.match(t["source"]["date_verified"]), t["id"]


def test_unverified_profiles_have_no_enabled_rules_and_record_blocker():
    for mid in ("pcbway", "xometry"):
        p = BY_ID[mid]
        assert p["profile_status"] == "unverified" and p["research"]["status"] == "blocked"
        assert not any(r["enabled"] for pr in p["processes"] for r in pr["rules"])
        assert not any(pr["materials"] for pr in p["processes"])   # no invented materials


def test_demo_profile_is_labelled_and_not_real():
    d = BY_ID["demo"]
    assert d["profile_status"] == "demo" and "DEMO" in d["manufacturer"]["name"] and "invented" in d["description"]


def test_sendcutsend_tables_are_complete_and_consistent():
    scs = BY_ID["sendcutsend"]["processes"][0]
    assert {m["id"] for m in scs["materials"]} == {"aluminum_5052_h32", "brass", "chromoly_4130", "copper", "galvanized_g90",
                                                  "mild_steel", "stainless_304", "stainless_316", "titanium_grade2"}
    for m in scs["materials"]:
        rows = m["thickness_specs"]
        ts = [r["thickness_mm"] for r in rows]
        assert ts == sorted(ts) and len(set(ts)) == len(ts)
        for r in rows:
            v = r["values"]
            if not r["bendable"]:
                assert v == {}
                continue
            assert 0 < v["k_factor"] < 1 and 0 < v["bend_radius_mm"] < 10 and v["die_width_mm"] >= 8
            assert v["min_flange_length_mm"] > v["bend_radius_mm"] and v["min_flange_flat_pattern_mm"] > 0
            # the flat-pattern minimum is never larger than the formed minimum (both published)
            assert v["min_flange_flat_pattern_mm"] <= v["min_flange_length_mm"] + 1e-6
            assert v["max_flat_size_mm"] == pytest.approx([762.0, 1117.6]) and v["min_flat_size_mm"][0] == pytest.approx(9.525)


def test_sendcutsend_values_match_the_saved_source_extract():
    src = json.load(open(os.path.join(DEFAULT_DIR, "sources", "sendcutsend_bending_tables_2026-10-20.json")))
    scs = BY_ID["sendcutsend"]["processes"][0]
    mild = next(m for m in scs["materials"] if m["id"] == "mild_steel")
    for srow, prow in zip(src["spec_table"]["Mild Steel"], mild["thickness_specs"]):
        assert prow["thickness_mm"] == pytest.approx(srow["thickness_in"] * 25.4, abs=1e-3)
        if srow["die_width_in"]:
            assert prow["values"]["die_width_mm"] == pytest.approx(srow["die_width_in"] * 25.4, abs=1e-3)
            assert prow["values"]["min_flange_length_mm"] == pytest.approx(srow["min_flange_in"] * 25.4, abs=1e-3)


def test_known_published_conflict_is_recorded_not_resolved():
    al = next(m for m in BY_ID["sendcutsend"]["processes"][0]["materials"] if m["id"] == "aluminum_5052_h32")
    row = next(r for r in al["thickness_specs"] if abs(r["thickness_mm"] - 0.080 * 25.4) < 1e-3)
    vals = sorted(c["value"] for c in row["conflicts"]["bend_radius_mm"])
    assert vals == pytest.approx([0.038 * 25.4, 0.045 * 25.4], abs=1e-3)


def test_na_rows_are_not_bendable():
    mild = next(m for m in BY_ID["sendcutsend"]["processes"][0]["materials"] if m["id"] == "mild_steel")
    for t_in in (0.313, 0.375, 0.5):
        row = next(r for r in mild["thickness_specs"] if abs(r["thickness_mm"] - t_in * 25.4) < 1e-3)
        assert row["bendable"] is False


# ---- validator behaviour on bad data -------------------------------------------------
def base():
    return copy.deepcopy(BY_ID["sendcutsend"])


def test_validator_rejects_bad_spec_data():
    p = base(); p["processes"][0]["materials"][0]["thickness_specs"][0]["values"]["die_width_mm"] = -1
    with pytest.raises(ProfileError):
        load_profile_dict(p)
    p = base(); p["processes"][0]["materials"][0]["thickness_specs"][0]["values"]["bogus"] = 1
    with pytest.raises(ProfileError):
        load_profile_dict(p)
    p = base(); p["processes"][0]["materials"][0]["thickness_specs"].append(copy.deepcopy(p["processes"][0]["materials"][0]["thickness_specs"][0]))
    with pytest.raises(ProfileError, match="duplicate thickness"):
        load_profile_dict(p)
    p = base(); del p["processes"][0]["materials"][0]["thickness_specs"][0]["source"]
    with pytest.raises(ProfileError):
        load_profile_dict(p)


def test_validator_rejects_spec_rule_without_data_and_undocumented_disabled_rules():
    p = base()
    p["processes"][0]["rules"].append({"id": "x", "type": "min_flange_length", "enabled": True, "verified": True,
                                       "parameters": {"spec": "bend_relief_depth_mm", "measure": "apex"}, "severity": "ERROR",
                                       "source": {"url": "https://x", "date_verified": "2026-01-01"},
                                       "applies_to": {"materials": []}})
    load_profile_dict(p)  # bend_relief_depth_mm exists for some material -> ok
    p["processes"][0]["rules"][-1]["parameters"]["spec"] = "k_factor"; load_profile_dict(p)
    p["processes"][0]["rules"][-1]["applies_to"] = {"materials": ["mild_steel"]}
    p["processes"][0]["materials"][5]["thickness_specs"] = []   # remove tables from mild_steel
    with pytest.raises(ProfileError, match="not defined"):
        load_profile_dict(p)
    q = base()
    q["processes"][0]["rules"][-1]["limitations"] = ""         # disabled rule with no explanation
    with pytest.raises(ProfileError, match="must say why"):
        load_profile_dict(q)


def test_validator_detects_conflicting_overlapping_rules():
    p = base()
    rules = p["processes"][0]["rules"]
    a = {"id": "dup1", "type": "min_hole_edge_distance", "enabled": True, "verified": True, "severity": "ERROR",
         "parameters": {"min_mm": 2}, "source": {"url": "https://x", "date_verified": "2026-01-01"}}
    b = dict(a, id="dup2", parameters={"min_mm": 3})
    rules += [a, b]
    out = load_profile_dict(p)
    assert any("dup1" in w and "dup2" in w for w in out["_warnings"])


def test_validator_rejects_bad_conflict_and_tolerance_data():
    p = base(); row = p["processes"][0]["materials"][0]["thickness_specs"][0]
    row["conflicts"] = {"bend_radius_mm": [{"value": 1, "source": {"url": "https://x", "date_verified": "2026-01-01"}}]}
    with pytest.raises(ProfileError, match=">= 2 candidates"):
        load_profile_dict(p)
    p = base(); p["processes"][0]["tolerances"][0]["source"] = {}
    with pytest.raises(ProfileError):
        load_profile_dict(p)
    p = base(); p["processes"][0]["thickness_match_tolerance_mm"] = 5
    with pytest.raises(ProfileError):
        load_profile_dict(p)


def test_schema_v1_profiles_still_load():
    load_profile_dict(json.load(open(os.path.join(os.path.dirname(__file__), "fixtures", "phase1_sendcutsend.json"))))


# ---- units -----------------------------------------------------------------------
def test_unit_conversion_roundtrip_and_formatting():
    assert in_to_mm(1) == 25.4 and mm_to_in(25.4) == 1 and in_to_mm(None) is None
    assert mm_to_in(in_to_mm(0.119)) == pytest.approx(0.119)
    assert fmt_len(7.62) == "7.62 mm (0.300 in)" and fmt_len(None) == "n/a"
