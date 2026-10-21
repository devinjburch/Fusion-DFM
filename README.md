# Fusion-DFM

Design-for-Manufacturability checks for **native Autodesk Fusion sheet metal**, evaluated against manufacturer
profiles (SendCutSend, PCBWay, Xometry, plus a fictional DEMO profile).

> **Status: Phase 1 prototype.** Engine, profiles and bridge are tested (`pytest`). The Fusion layer was checked against the
> official API reference ([docs/API_VERIFICATION.md](docs/API_VERIFICATION.md)) but **has not been run inside Fusion**; follow
> [docs/FIRST_RUN.md](docs/FIRST_RUN.md). See [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

| Folder | Purpose |
|---|---|
| `dfm_engine/` | CAD-independent models, profile validation, rules evaluation (no `adsk` imports) |
| `manufacturers/` | JSON profiles with source URL + verification date per rule |
| `fusion_addin/` | Fusion integration: toolbar button, palette UI, geometry extraction, highlighting |
| `ai_assistant/` | Redesign workflow architecture (schemas, approval state machine, mock CAD adapter); no AI, no CAD writes |
| `smoke_test/` | Fusion script that checks toolbar, design access, thickness extraction, results display |
| `tests/` | Automated tests (`pip install -r requirements-dev.txt && pytest`) |
| `docs/` | [Install](docs/INSTALL.md) · [First run](docs/FIRST_RUN.md) · [API verification](docs/API_VERIFICATION.md) · [Architecture](docs/ARCHITECTURE.md) · [Profiles](docs/PROFILES.md) · [Manufacturers](docs/MANUFACTURERS.md) · [AI architecture](docs/AI_ARCHITECTURE.md) · [Progress](docs/PROGRESS.md) · [Limitations](docs/LIMITATIONS.md) · [Testing](docs/TESTING.md) |

Quick start: `python scripts/install.py`, then run **FusionDFM** from Fusion's Scripts and Add-Ins dialog; click
**Check Manufacturability** (Design workspace → Utilities).
