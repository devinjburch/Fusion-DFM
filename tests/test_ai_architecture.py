"""Redesign-workflow architecture on a MOCK CAD model (no AI, no network, no real CAD)."""
import json
import os
import pytest
from ai_assistant import (RedesignSession, WorkflowError, InMemoryCadAdapter, FusionCadAdapterStub, DesignConstraint,
                          AffectedFeature, ParameterChange, SuggestedCorrection, ManufacturingProblem, State, problems_from_report)
from ai_assistant.cad_adapter import AdapterError
from dfm_engine import PartModel, Flange, Bend, GeometryRef, evaluate, load_profile
from dfm_engine.profile import DEFAULT_DIR

IN = 25.4
SCS = load_profile(os.path.join(DEFAULT_DIR, "sendcutsend.json"))
TOK = "flange-1"


def make(initial=0.30, extra_params=None):
    params = {TOK: {"flange_length": initial * IN}}
    params.update(extra_params or {})
    cad = InMemoryCadAdapter(params)

    def analyze():
        apex = cad.parameters[TOK]["flange_length"]
        part = PartModel("Mock part", thickness_mm=0.119 * IN, material_name="Mild Steel", flat_dimensions_mm=(300, 100),
                         bends=[Bend(0.063 * IN, 90, 100, GeometryRef("bend", "bend-1", "Bend 1"))],
                         flanges=[Flange(length_mm=apex - 0.18 * IN, length_apex_mm=apex, bend_angle_deg=90, ref=GeometryRef("flange", TOK, "Flange 1"))])
        return evaluate(part, SCS, "sheet_metal_bending")
    return cad, analyze


def session(**kw):
    cad, analyze = make(**{k: v for k, v in kw.items() if k in ("initial", "extra_params")})
    rep = analyze()
    problems = problems_from_report(rep)
    assert len(problems) == 1, [p.rule_id for p in problems]
    return RedesignSession(problems[0], cad, analyze, kw.get("constraints")), cad


def happy_path(s):
    s.explain()
    cands = s.propose()
    shown = s.show(cands[0].correction_id)
    s.approve("devin", shown)
    s.apply()
    return s.reanalyze()


def test_problem_extraction_only_confirmed_requirements():
    cad, analyze = make()
    ps = problems_from_report(analyze())
    assert [p.rule_id for p in ps] == ["scs.min_flange_length"]
    p = ps[0]
    assert p.feature.ref_token == TOK and p.feature.kind == "flange" and p.required_mm == pytest.approx(0.466 * IN, abs=1e-3)
    assert p.source_url.startswith("https://sendcutsend.com")


def test_full_workflow_detect_to_accept():
    s, cad = session()
    out = happy_path(s)
    assert out["problem_resolved"] and out["new_failures"] == [] and out["recommend"] == "accept"
    assert cad.parameters[TOK]["flange_length"] == pytest.approx(0.466 * IN, abs=1e-3)
    s.accept()
    assert s.state == State.ACCEPTED
    states = [e[1] for e in s.log]
    assert states == ["DETECTED", "EXPLAINED", "PROPOSED", "PROPOSED", "AWAITING_APPROVAL", "APPROVED", "APPLIED", "REANALYZED", "ACCEPTED"]


def test_undo_restores_exact_original_values_and_cannot_repeat():
    s, cad = session()
    before = cad.parameters[TOK]["flange_length"]
    happy_path(s)
    assert cad.parameters[TOK]["flange_length"] != before
    s.undo()
    assert cad.parameters[TOK]["flange_length"] == before and s.state == State.UNDONE and s.selected.status == "rolled_back"
    with pytest.raises(WorkflowError):
        s.undo()


def test_cannot_modify_model_without_approval():
    s, cad = session()
    before = dict(cad.parameters[TOK])
    with pytest.raises(WorkflowError):
        s.apply()                                   # straight from DETECTED
    s.explain(); cands = s.propose()
    with pytest.raises(WorkflowError):
        s.apply()                                   # proposed but not shown/approved
    s.show(cands[0].correction_id)
    with pytest.raises(WorkflowError):
        s.apply()                                   # shown but not approved
    with pytest.raises(WorkflowError):
        s.approve("", "text")                       # approval needs identity
    assert cad.parameters[TOK] == before


def test_rejection_is_terminal_and_leaves_model_untouched():
    s, cad = session()
    s.explain(); cands = s.propose(); s.show(cands[0].correction_id)
    before = dict(cad.parameters[TOK])
    s.reject("not now")
    assert s.state == State.REJECTED and cad.parameters[TOK] == before
    with pytest.raises(WorkflowError):
        s.approve("devin", "x")


def test_illegal_transitions_rejected():
    s, _ = session()
    with pytest.raises(WorkflowError):
        s.propose()                                 # must explain first
    with pytest.raises(WorkflowError):
        s.reanalyze()
    with pytest.raises(WorkflowError):
        s.accept()


def test_locked_parameter_constraint_blocks_the_correction():
    lock = DesignConstraint("locked_parameter", "mating part depends on this flange", AffectedFeature("flange", TOK), "flange_length")
    s, cad = session(constraints=[lock])
    s.explain(); cands = s.propose()
    assert not cands[0].applicable and "locked" in cands[0].violated_constraints[0]
    with pytest.raises(WorkflowError, match="violates design constraints"):
        s.show(cands[0].correction_id)


def test_max_change_constraint():
    limit = DesignConstraint("max_change_mm", "keep flange within 2 mm of design", AffectedFeature("flange", TOK), "flange_length", 2.0)
    s, _ = session(constraints=[limit])           # needs +4.2 mm -> blocked
    s.explain(); c = s.propose()[0]
    assert not c.applicable and "exceeds" in c.violated_constraints[0]
    ok = DesignConstraint("max_change_mm", "generous", AffectedFeature("flange", TOK), "flange_length", 50.0)
    s2, _ = session(constraints=[ok]); s2.explain()
    assert s2.propose()[0].applicable


def test_new_failures_after_change_recommend_undo():
    s, cad = session()
    s.explain(); c = s.propose()[0]
    shown = s.show(c.correction_id); s.approve("devin", shown)
    orig = s.analyze
    def worse():                                    # simulate a side effect: the change breaks flat size
        r = orig()
        from dfm_engine.models import Status
        extra = next(x for x in r.results if x.rule_id == "scs.max_flat_size")
        extra.status = Status.FAIL
        return r
    s.analyze = worse
    s.apply()
    out = s.reanalyze()
    assert out["recommend"] == "undo" and ("scs.max_flat_size", None) in out["new_failures"]
    with pytest.raises(WorkflowError):
        s.accept()
    s.undo()
    assert s.state == State.UNDONE


def test_stale_proposal_is_refused_by_adapter():
    s, cad = session()
    s.explain(); c = s.propose()[0]; s.approve("devin", s.show(c.correction_id))
    cad.parameters[TOK]["flange_length"] += 1.0     # the model changed after the proposal
    with pytest.raises(AdapterError, match="changed since the proposal"):
        s.apply()
    assert s.state == State.APPROVED


def test_adapter_is_all_or_nothing():
    cad = InMemoryCadAdapter({"a": {"x": 1.0}, "b": {"y": 2.0}})
    f = lambda t, p, a, b: ParameterChange(AffectedFeature("body", t), p, a, b)
    with pytest.raises(AdapterError):
        cad.apply_changes("c1", [f("a", "x", 1.0, 5.0), f("b", "missing", 2.0, 3.0)])
    assert cad.parameters["a"]["x"] == 1.0


def test_fusion_adapter_stub_never_writes():
    stub = FusionCadAdapterStub()
    for call in (lambda: stub.read_parameter("t", "p"), lambda: stub.apply_changes("c", []), lambda: stub.undo(None)):
        with pytest.raises(NotImplementedError):
            call()


def test_models_serialise_and_roundtrip_json():
    s, _ = session()
    happy_path(s)
    d = json.loads(json.dumps(s.to_dict()))
    assert d["state"] == "REANALYZED" and d["approval"]["approved_by"] == "devin" and d["rollback"]["operations"]
    c = SuggestedCorrection.from_dict(d["candidates"][0])
    assert c.changes[0].to_value_mm == pytest.approx(0.466 * IN, abs=1e-3) and c.validations
    p = ManufacturingProblem.from_dict(d["problem"])
    assert p.feature.ref_token == TOK
    inv = c.changes[0].inverse()
    assert inv.to_value_mm == c.changes[0].from_value_mm


def test_example_artifact_is_current():
    """ai_assistant/examples/flange_length_session.json is generated by the mock workflow (see docs); keep it in sync."""
    s, _ = session()
    happy_path(s)
    d = s.to_dict()
    for k in ("log",):
        d.pop(k)
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ai_assistant", "examples", "flange_length_session.json")
    if os.environ.get("UPDATE_EXAMPLES"):
        json.dump(_stable(d), open(path, "w"), indent=1)
    ex = json.load(open(path))
    assert ex["state"] == "REANALYZED" and ex["problem"]["rule_id"] == d["problem"]["rule_id"]
    assert ex["candidates"][0]["changes"][0]["to_value_mm"] == pytest.approx(d["candidates"][0]["changes"][0]["to_value_mm"])


def _stable(d):
    d = json.loads(json.dumps(d))
    d["approval"]["approved_at"] = "<timestamp>"
    for o in d["rollback"]["operations"]:
        o["created_at"] = "<timestamp>"
    return d


def test_no_network_or_ai_imports_in_package():
    import pathlib, re
    root = pathlib.Path(__file__).resolve().parent.parent / "ai_assistant"
    banned = re.compile(r"^\s*(import|from)\s+(requests|urllib|http|socket|anthropic|openai|httpx|aiohttp)\b", re.M)
    for f in root.glob("*.py"):
        assert not banned.search(f.read_text()), f.name
