import copy, json, os
import pytest
from dfm_engine import list_profiles, load_profile, load_profile_dict, ProfileError
from dfm_engine.profile import DEFAULT_DIR


def test_all_shipped_profiles_valid():
    profiles, errors = list_profiles()
    assert errors == []
    assert {p["manufacturer"]["id"] for p in profiles} == {"sendcutsend", "pcbway", "xometry", "demo"}


def test_demo_profile_clearly_labelled():
    p = load_profile(os.path.join(DEFAULT_DIR, "demo.json"))
    assert p["profile_status"] == "demo" and "DEMO" in p["manufacturer"]["name"]


def test_unverified_profiles_have_no_enabled_rules():
    p = load_profile(os.path.join(os.path.dirname(__file__), "fixtures", "phase1_pcbway_unverified.json"))
    assert p["profile_status"] == "unverified"
    assert not any(r["enabled"] for pr in p["processes"] for r in pr["rules"])


def test_pcbway_xometry_data_is_provisional_and_non_blocking():
    for mid in ("pcbway", "xometry"):
        p = load_profile(os.path.join(DEFAULT_DIR, f"{mid}.json"))
        enabled = [r for pr in p["processes"] for r in pr["rules"] if r["enabled"]]
        assert enabled and all(r["provisional"] and r["consequence"] in ("warning", "review") for r in enabled)


def test_enabled_real_rules_have_source_and_date():
    p = load_profile(os.path.join(DEFAULT_DIR, "sendcutsend.json"))
    for r in p["processes"][0]["rules"]:
        if r["enabled"]:
            assert r["verified"] and r["source"]["url"].startswith("https://") and r["source"]["date_verified"]


def _base():
    return {"schema_version": 1, "manufacturer": {"id": "x", "name": "X"}, "profile_status": "verified",
            "processes": [{"id": "p", "materials": [{"id": "m", "name": "M"}], "rules": []}]}


def _rule(**kw):
    r = {"id": "r1", "type": "min_bend_radius", "enabled": True, "verified": True,
         "parameters": {"min_mm": 1}, "source": {"url": "https://x", "date_verified": "2026-01-01"}}
    r.update(kw)
    return r


def _with(rule):
    d = _base(); d["processes"][0]["rules"] = [rule]; return d


def test_valid_minimal():
    load_profile_dict(_with(_rule()))


@pytest.mark.parametrize("mut", [
    {"verified": False},                       # enabled but unverified in real profile
    {"source": {}},                            # missing source
    {"parameters": {}},                        # enabled without parameters
    {"parameters": {"min_mm": -1}},
    {"parameters": {"bogus": 1}},
    {"type": "nope"},
    {"severity": "CRITICAL"},
    {"applies_to": {"materials": ["ghost"]}},
    {"enabled": "yes"},
])
def test_invalid_rules_rejected(mut):
    with pytest.raises(ProfileError):
        load_profile_dict(_with(_rule(**mut)))


def test_duplicate_rule_ids_rejected():
    d = _base(); d["processes"][0]["rules"] = [_rule(), _rule()]
    with pytest.raises(ProfileError):
        load_profile_dict(d)


def test_missing_top_level_keys():
    d = _base(); del d["processes"]
    with pytest.raises(ProfileError):
        load_profile_dict(d)


def test_bad_json_file(tmp_path):
    f = tmp_path / "bad.json"; f.write_text("{nope")
    with pytest.raises(ProfileError):
        load_profile(str(f))
    (tmp_path / "ok.json").write_text(json.dumps(_with(_rule())))
    profiles, errors = list_profiles(str(tmp_path))
    assert len(profiles) == 1 and len(errors) == 1  # one bad file does not hide the good one


def test_thickness_range_needs_both_bounds():
    with pytest.raises(ProfileError):
        load_profile_dict(_with(_rule(type="thickness_range", parameters={"min_mm": 1})))
