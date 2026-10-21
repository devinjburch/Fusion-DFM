# Phase 2 progress

Branch: `feature/phase2-manufacturing` (from `feature/phase1-mvp`; Phase 1 untouched as baseline).

## Done
- [x] Manufacturer DB schema v2 (per-thickness spec tables, spec-driven rules, strength, conflicts, tolerances, restrictions, research status)
- [x] SendCutSend profile rebuilt from published tables (see MANUFACTURERS.md)
- [x] Engine v2: stock-thickness matching, fixed-radius rule, apex flange rule, die-width/centerline rule, conflicts, advisory rules, corrections
## In progress / remaining
See the checklist at the bottom of this file as it is updated.

## Blockers
- PCBWay and Xometry documentation unreachable from the build environment (DNS/proxy failures on 2026-10-20). Their profiles stay unverified.
- No Fusion runtime in the build environment: everything touching Fusion needs local testing (see TESTING.md).
