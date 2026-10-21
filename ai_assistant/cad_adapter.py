"""CAD access boundary for the redesign workflow. Only the in-memory mock is implemented."""
from __future__ import annotations
from typing import Protocol
from .models import ParameterChange, UndoOperation


class CadAdapter(Protocol):
    def read_parameter(self, token: str, parameter: str) -> float: ...
    def apply_changes(self, correction_id: str, changes: list) -> UndoOperation: ...
    def undo(self, op: UndoOperation) -> None: ...


class AdapterError(RuntimeError):
    pass


class InMemoryCadAdapter:
    """Mock CAD model: {token: {parameter: value_mm}}. Used for tests and demos; touches no real CAD."""

    def __init__(self, parameters: dict):
        self.parameters = {t: dict(p) for t, p in parameters.items()}
        self.history = []

    def read_parameter(self, token, parameter):
        try:
            return self.parameters[token][parameter]
        except KeyError as e:
            raise AdapterError(f"unknown parameter {parameter!r} on {token!r}") from e

    def apply_changes(self, correction_id, changes):
        inverse = []
        for c in changes:                          # validate everything first: all-or-nothing
            cur = self.read_parameter(c.target.ref_token, c.parameter)
            if c.from_value_mm is not None and abs(cur - c.from_value_mm) > 1e-6:
                raise AdapterError(f"{c.parameter} changed since the proposal ({cur} != {c.from_value_mm}); re-analyse first")
        for c in changes:
            cur = self.read_parameter(c.target.ref_token, c.parameter)
            inverse.append(ParameterChange(c.target, c.parameter, c.to_value_mm, cur, c.units))
            self.parameters[c.target.ref_token][c.parameter] = c.to_value_mm
        op = UndoOperation(correction_id, list(reversed(inverse)), snapshot_ref=f"mem-{len(self.history)}")
        self.history.append(correction_id)
        return op

    def undo(self, op):
        if op.executed:
            raise AdapterError("undo operation already executed")
        for c in op.inverse_changes:
            self.parameters[c.target.ref_token][c.parameter] = c.to_value_mm
        op.executed = True


class FusionCadAdapterStub:
    """PLACEHOLDER for the future Fusion implementation. Deliberately unimplemented.

    Intended mapping (to be verified against the Fusion API when this phase starts):
      read/apply  -> ModelParameter.expression/value of the sheet-metal feature or sketch dimension that drives the feature
                     (Design.allParameters / Feature.parameters), applied inside one TimelineGroup or between timeline markers
      undo        -> restore the previous expressions (parameter_restore) or roll the timeline marker back (timeline_rollback)
    Every write must be preceded by an explicit ApprovalRecord; this stub never writes.
    """

    def read_parameter(self, token, parameter):
        raise NotImplementedError("Fusion write/read adapter is not implemented in Phase 2")

    def apply_changes(self, correction_id, changes):
        raise NotImplementedError("Fusion CAD modification is not implemented in Phase 2")

    def undo(self, op):
        raise NotImplementedError("Fusion CAD modification is not implemented in Phase 2")
