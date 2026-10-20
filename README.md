# Fusion-DFM

Design-for-Manufacturability checks for **native Autodesk Fusion sheet metal**, evaluated against manufacturer
profiles (SendCutSend, PCBWay, Xometry, plus a fictional DEMO profile).

> **Status: Phase 1 prototype.** The rules engine, profiles and bridge are tested (`pytest`). The Fusion API layer
> (`fusion_addin/extraction.py`) was written from the documented API but **has not been run inside Fusion**; expect
> to debug it on first launch. See [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

| Folder | Purpose |
|---|---|
| `dfm_engine/` | CAD-independent models, profile validation, rules evaluation (no `adsk` imports) |
| `manufacturers/` | JSON profiles with source URL + verification date per rule |
| `fusion_addin/` | Fusion integration: toolbar button, palette UI, geometry extraction, highlighting |
| `ai_assistant/` | Reserved, empty |
| `tests/` | Automated tests (`pip install -r requirements-dev.txt && pytest`) |
| `docs/` | [Install](docs/INSTALL.md) · [Architecture](docs/ARCHITECTURE.md) · [Profiles](docs/PROFILES.md) · [Limitations](docs/LIMITATIONS.md) · [Testing](docs/TESTING.md) |

Quick start: `python scripts/install.py`, then run **FusionDFM** from Fusion's Scripts and Add-Ins dialog; click
**Check Manufacturability** (Design workspace → Utilities).
