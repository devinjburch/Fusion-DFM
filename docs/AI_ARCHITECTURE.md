# AI-assisted redesign: architecture (Phase 2 = design + tests only)

Nothing in `ai_assistant/` calls an AI service, uses the network, or modifies CAD. The Fusion adapter is a stub that raises `NotImplementedError`.

## Workflow (state machine in `ai_assistant/workflow.py`)
`DETECTED → EXPLAINED → PROPOSED → AWAITING_APPROVAL → APPROVED → APPLIED → REANALYZED → ACCEPTED`, with `REJECTED` / `UNDONE` exits.
No path reaches `APPLIED` without an `ApprovalRecord` (user identity + the exact text shown) for *that* correction. Re-analysis recommends
`accept` only if the target rule passes and no new FAIL appears; otherwise it recommends `undo`. Undo restores recorded original values and cannot run twice.

## Data models (`ai_assistant/models.py`, all JSON-serialisable)
`ManufacturingProblem` (rule, feature, measured/required, source) · `AffectedFeature` (kind, Fusion entityToken, driving CAD parameter, owner feature) ·
`ParameterChange` (from/to, inverse) · `SuggestedCorrection` (changes, confidence, side effects, validations, violated constraints) ·
`DesignConstraint` (locked parameter, max change, keep thickness/material) · `ValidationRequirement` · `ApprovalRecord` · `UndoOperation` / `RollbackPlan`.

## Extension points
- `CorrectionGenerator` protocol: `RuleBasedGenerator` converts the engine's `Correction`s today; a future LLM generator implements the same interface and its
  output still passes through constraint checks, approval, re-analysis and undo. Model output must never bypass `RedesignSession`.
- `CadAdapter` protocol: `InMemoryCadAdapter` (tests). A Fusion adapter would map parameters to `ModelParameter` expressions inside one timeline group
  (to be verified against the API then) and must refuse stale proposals (the mock already does).
- Known semantic gap: flange length is measured to the *apex* for SendCutSend; a CAD adapter must translate between apex length and the driving dimension.

Example artifact: `ai_assistant/examples/flange_length_session.json` (generated from the mock flow; `UPDATE_EXAMPLES=1 pytest` regenerates it).
