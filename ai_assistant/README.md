# ai_assistant (reserved)

Placeholder for Phase 3+: proposing and executing controlled model corrections. No AI API integration exists yet.
Intended contract: consume `dfm_engine.Report` results (each carries rule id, measured/required values and a
`GeometryRef`) and emit *proposed* parametric edits that the user must approve. Nothing here is imported by the add-in.
