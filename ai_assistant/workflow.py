"""The redesign workflow as an explicit state machine with an audit log.

detect -> explain -> propose -> show -> APPROVE -> apply -> reanalyse -> accept | undo
No step that changes the model is reachable without an ApprovalRecord for exactly that correction.
"""
from __future__ import annotations
from typing import Callable, Optional
from dfm_engine.models import Report, Status
from .cad_adapter import CadAdapter
from .models import (State, ManufacturingProblem, SuggestedCorrection, DesignConstraint, ApprovalRecord, UndoOperation,
                     RollbackPlan, _now)
from .planner import CorrectionGenerator, RuleBasedGenerator, problems_from_report


class WorkflowError(RuntimeError):
    pass


_ALLOWED = {
    State.DETECTED: {State.EXPLAINED, State.REJECTED},
    State.EXPLAINED: {State.PROPOSED, State.REJECTED},
    State.PROPOSED: {State.AWAITING_APPROVAL, State.REJECTED},
    State.AWAITING_APPROVAL: {State.APPROVED, State.PROPOSED, State.REJECTED},
    State.APPROVED: {State.APPLIED, State.REJECTED},
    State.APPLIED: {State.REANALYZED, State.UNDONE},
    State.REANALYZED: {State.ACCEPTED, State.UNDONE},
    State.ACCEPTED: {State.UNDONE},
    State.UNDONE: set(), State.REJECTED: set(),
}


class RedesignSession:
    """One problem, one chosen correction. `analyze` re-runs the DFM analysis against the (mock or real) model."""

    def __init__(self, problem: ManufacturingProblem, cad: CadAdapter, analyze: Callable[[], Report],
                 constraints: Optional[list] = None, generator: Optional[CorrectionGenerator] = None):
        self.problem, self.cad, self.analyze = problem, cad, analyze
        self.constraints = list(constraints or [])
        self.generator = generator or RuleBasedGenerator()
        self.state = State.DETECTED
        self.candidates: list = []
        self.selected: Optional[SuggestedCorrection] = None
        self.approval: Optional[ApprovalRecord] = None
        self.undo_stack: list = []
        self.reanalysis: Optional[dict] = None
        self.log: list = [(_now(), State.DETECTED.value, f"detected {problem.rule_id}")]
        self._baseline = analyze()

    # ---- plumbing
    def _go(self, new: State, note=""):
        if new not in _ALLOWED[self.state]:
            raise WorkflowError(f"illegal transition {self.state.value} -> {new.value}")
        self.state = new
        self.log.append((_now(), new.value, note))

    # ---- steps
    def explain(self) -> str:
        self._go(State.EXPLAINED)
        p = self.problem
        return f"{p.explanation} (rule {p.rule_id}; source: {p.source_url or 'n/a'})"

    def propose(self) -> list:
        self._go(State.PROPOSED)
        self.candidates = self.generator.generate(self.problem, self._baseline, self.constraints)
        if not self.candidates:
            raise WorkflowError("no correction could be generated for this problem")
        self.log.append((_now(), "PROPOSED", f"{len(self.candidates)} candidate(s)"))
        return self.candidates

    def show(self, correction_id: str) -> str:
        """Select one candidate and return the text the user must see before approving."""
        c = next((x for x in self.candidates if x.correction_id == correction_id), None)
        if c is None:
            raise WorkflowError("unknown correction")
        if not c.applicable:
            raise WorkflowError("correction violates design constraints: " + "; ".join(c.violated_constraints))
        self._go(State.AWAITING_APPROVAL)
        self.selected = c
        lines = [f"Proposed change: {c.title}", f"Why: {c.rationale}"]
        if c.side_effects:
            lines.append("Side effects: " + "; ".join(c.side_effects))
        lines.append("This will modify your CAD model. You can undo it afterwards.")
        return "\n".join(lines)

    def approve(self, user: str, shown_summary: str) -> ApprovalRecord:
        if self.state != State.AWAITING_APPROVAL or self.selected is None:
            raise WorkflowError("nothing is awaiting approval")
        if not user or not shown_summary:
            raise WorkflowError("approval needs a user identity and the text that was shown")
        self.approval = ApprovalRecord(self.selected.correction_id, user, shown_summary=shown_summary)
        self.selected.status = "approved"
        self._go(State.APPROVED, f"approved by {user}")
        return self.approval

    def reject(self, reason=""):
        self._go(State.REJECTED, reason)
        if self.selected:
            self.selected.status = "rejected"

    def apply(self) -> UndoOperation:
        if self.state != State.APPROVED or self.approval is None or self.selected is None \
                or self.approval.correction_id != self.selected.correction_id:
            raise WorkflowError("explicit approval of this exact correction is required before modifying the model")
        for con in self.constraints:
            for ch in self.selected.changes:
                v = con.violated_by(ch)
                if v:
                    raise WorkflowError("constraint violated: " + v)
        op = self.cad.apply_changes(self.selected.correction_id, self.selected.changes)
        self.undo_stack.append(op)
        self.selected.status = "applied"
        self._go(State.APPLIED, f"applied; undo op {op.op_id}")
        return op

    def reanalyze(self) -> dict:
        if self.state != State.APPLIED:
            raise WorkflowError("nothing applied to re-analyse")
        after = self.analyze()
        key = lambda r: (r.rule_id, r.geometry_ref.token if r.geometry_ref else None)
        before_fail = {key(r) for r in self._baseline.results if r.status == Status.FAIL}
        after_fail = {key(r) for r in after.results if r.status == Status.FAIL}
        token = self.problem.feature.ref_token
        resolved = (self.problem.rule_id, token) not in after_fail
        new_failures = sorted(after_fail - before_fail)
        self.reanalysis = {"problem_resolved": resolved, "new_failures": new_failures, "overall_before": self._baseline.overall.value,
                           "overall_after": after.overall.value, "recommend": "accept" if resolved and not new_failures else "undo"}
        self._go(State.REANALYZED, f"resolved={resolved} new_failures={len(new_failures)}")
        return self.reanalysis

    def accept(self):
        if self.state != State.REANALYZED or not self.reanalysis or self.reanalysis["recommend"] != "accept":
            raise WorkflowError("only a re-analysed change that resolved the problem without new failures can be accepted")
        self._go(State.ACCEPTED)

    def undo(self):
        if not self.undo_stack or self.state not in (State.APPLIED, State.REANALYZED, State.ACCEPTED):
            raise WorkflowError("nothing to undo")
        op = self.undo_stack[-1]
        self.cad.undo(op)
        self.undo_stack.pop()
        if self.selected:
            self.selected.status = "rolled_back"
        self._go(State.UNDONE, f"undo {op.op_id}")

    def rollback_plan(self) -> RollbackPlan:
        return RollbackPlan(list(reversed(self.undo_stack)))

    def to_dict(self):
        return {"state": self.state.value, "problem": self.problem.to_dict(),
                "constraints": [c.to_dict() for c in self.constraints],
                "candidates": [c.to_dict() for c in self.candidates],
                "selected": self.selected.correction_id if self.selected else None,
                "approval": self.approval.to_dict() if self.approval else None,
                "reanalysis": self.reanalysis, "rollback": self.rollback_plan().to_dict(),
                "log": [{"at": a, "state": b, "note": c} for a, b, c in self.log]}
