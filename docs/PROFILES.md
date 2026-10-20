# Manufacturer profile format (`manufacturers/*.json`, schema_version 1)

```
manufacturer{id,name,website}, profile_status: verified|partially_verified|unverified|demo, description,
processes[{ id,name, materials[{id,name,aliases[]}], notes[], rules[{
   id, type, enabled, verified, severity, parameters{...}, applies_to{materials[],thickness_mm{min,max}},
   source{url,date_verified,note}, limitations }] }]
```
Validation (`dfm_engine/profile.py`): unique ids; known rule types/parameters; non-negative numbers; in a non-demo profile an
**enabled rule must be `verified` with `source.url` and `source.date_verified`**. Unknown/unverified values stay `enabled:false`
with empty `parameters`. Material matching is by case-insensitive alias substring (longest wins); no match → NEEDS_REVIEW, and the
user can pick a material in the palette.

## Research status (retrieved 2026-10-20)
- **SendCutSend** (`https://sendcutsend.com/guidelines/bending/`): enabled = per-material thickness *ranges* (9 materials), max flat
  part 30"×44", laser-cut min hole = 50% thickness. Disabled = bend radius, flange length, hole-edge, hole-bend (per-thickness
  tables not available in the page text). Noted but not modelled: U/C-channel base ≥2× flange; box max flange 5".
- **PCBWay, Xometry**: the build environment's network policy blocked these sites, so **no data was entered**; all rules disabled.
  To complete: open their official sheet-metal design guides, enter values with `source.url` + `date_verified`, set `enabled/verified`.
- **demo**: fictional, flagged `demo` everywhere in the UI.
