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


## Rule consequence and the WARNING status (added after field round 5)
`"consequence": "blocking"` (default) or `"warning"`. For a `warning` rule (requirement strength only) a confirmed violation *and* an unresolved check become the
non-blocking status **WARNING** (severity WARNING; unresolved ones carry `confirmed: false` and the text "Not confirmed"). A WARNING never fails the part and never counts as a pass:
the single-manufacturer overall status is `WARNING` ("pass with warnings") and the comparison verdict is *Conditionally compatible* with the warnings listed. A `warning` rule must justify
itself in `notes` or `rationale` (validator-enforced). Material/thickness pre-checks (e.g. unmatched material) still give NEEDS_REVIEW. Set `"consequence": "blocking"` to restore failing behaviour.
Every result also has a `title` such as "Hole 4: too close to bend" / "Hole 1: may be too close to bend" (unconfirmed).
