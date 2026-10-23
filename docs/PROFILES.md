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


## Decisions from field round 6 (2026-10-23)
- **Unchecked non-blocking rules stay NEEDS_REVIEW.** For a `consequence: warning` rule, WARNING means a *measured* outcome: a confirmed violation, or a measured-but-borderline case (`borderline`, `confirmed: false`).
  Anything that could not be evaluated (no spec table, unmatched material, unmeasured feature, uncertain classification) remains NEEDS_REVIEW, and its title says "could not be checked" instead of asserting a finding.
- `consequence: review`: a confirmed exceedance of a nominal/typical limit becomes NEEDS_REVIEW ("confirm with the manufacturer"), never FAIL or WARNING.
- `provisional: true` (requires `source.provenance`, must be non-blocking): second-hand data. PASS results are labelled "(provisional data ...)", and provisional rules never count toward requirement coverage, so they cannot yield a COMPATIBLE verdict.
- `strength: advisory`: a measured miss is a low-severity (INFO) WARNING.
- `restrictions` (per process) are published requirements the tool does not evaluate; they are listed in the palette and in the HTML report under "Published requirements not evaluated".
