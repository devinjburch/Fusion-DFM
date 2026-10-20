# Limitations

## Needs live verification (not executed inside Fusion)
`fusion_addin/` was written against the documented API from memory of its classes; the authoring environment had no Fusion and
the API reference was not retrievable. Verify first on a real sheet metal part:
- `body.isSheetMetal`, `component.activeSheetMetalRule`, `rule.thickness.value`, `component.flatPattern`, `flatPattern.flatBody(ies)`:
  names are **probed with `getattr`** and fall back to "unsupported"; confirm which exist.
- Palette HTML path/URL form, `Arc3D.startAngle/endAngle`, `CurveEvaluator3D.getStrokes`, `BRepFace.tempId` usage.
- Toolbar panel id `SolidScriptsAddinsPanel`.

## Extraction approach and known gaps
| Item | Method | Caveat |
|---|---|---|
| Thickness | sheet metal rule if exposed, else min distance between opposed parallel planar faces | geometry-derived value labelled `derived_from_geometry` |
| Material | body/component material name | generic Fusion materials ("Steel") won't match a manufacturer material → pick one in the UI |
| Bend radius | coaxial cylinder pair → smaller radius = inner | single-surface bends reported as unmeasured |
| Flange length | on the face tangent to the inner bend surface, tangent line → farthest edge point | manufacturers may define it differently (e.g. from bend line / outside mold line); only free (single-bend) flanges are checked |
| Holes | cylindrical faces bounded by two coaxial full circles, t apart | **slots, non-circular cutouts, blind/countersunk holes are not extracted**; hole-to-hole spacing unchecked |
| Hole-to-edge | hole edge → nearest non-bend, non-circle edge on the same face | includes inner cutout edges; measured in-plane approximations |
| Hole-to-bend | hole edge → tangent line of bend on the same face | holes on faces with no bend are treated as N/A |
| Flat size | flat pattern bbox if API exposes it | axis-aligned; rotated pattern may overestimate; unavailable → NEEDS_REVIEW |
| Overall size | folded axis-aligned bbox (informational) | |
Multiple bodies: selected body, else largest sheet metal body (warned). Only the first process/material combination chosen is evaluated.
Highlighting is via Fusion selection (not custom graphics).
