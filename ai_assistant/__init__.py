"""AI-assisted redesign ARCHITECTURE (Phase 2: schemas, state machine, mock adapter, tests only).

Nothing here calls an AI service, touches the network, or modifies real CAD geometry.
"""
from .models import (AffectedFeature, ParameterChange, DesignConstraint, ValidationRequirement, ManufacturingProblem,
                     SuggestedCorrection, UndoOperation, RollbackPlan, ApprovalRecord, State)
from .workflow import RedesignSession, WorkflowError
from .planner import problems_from_report, RuleBasedGenerator, CorrectionGenerator
from .cad_adapter import CadAdapter, InMemoryCadAdapter, FusionCadAdapterStub

__all__ = [n for n in dir() if not n.startswith("_")]
