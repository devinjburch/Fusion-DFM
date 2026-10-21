# Limitations

## API verification status
The Fusion API layer has been checked member-by-member against the official reference and corrected (see
[API_VERIFICATION.md](API_VERIFICATION.md)), but **it has never been run inside Fusion**. Items still unconfirmed: toolbar panel id,
manifest field set, `file:///` palette URL, and the geometry-classification assumptions listed there.

## Extraction approach and known gaps
| Item | Method | Caveat |
|---|---|---|
| Thickness | sheet metal rule if exposed, else min distance between opposed parallel planar faces | geometry-derived value labelled `derived_from_geometry` |
| Material | body/component material name | generic Fusion materials ("Steel") won't match a manufacturer material → pick one in the UI |
| Bend radius | coaxial cylinder pair → smaller radius = inner | single-surface bends reported as unmeasured |
| Flanges | both faces beside a bend are listed (e.g. base and upright of an L) | |
| Flange length | on the face tangent to the inner bend surface, tangent line → farthest edge point | manufacturers may define it differently (e.g. from bend line / outside mold line); only free (single-bend) flanges are checked |
| Holes | cylindrical faces bounded by two coaxial full circles, t apart | **slots, non-circular cutouts, blind/countersunk holes are not extracted**; hole-to-hole spacing unchecked |
| Hole-to-edge | hole edge → nearest non-bend, non-circle edge on the same face | includes inner cutout edges; measured in-plane approximations |
| Hole-to-bend | hole edge → tangent line of bend on the same face | holes on faces with no bend are treated as N/A |
| Flat size | flat pattern bbox if API exposes it | axis-aligned; rotated pattern may overestimate; unavailable → NEEDS_REVIEW |
| Overall size | folded axis-aligned bbox (informational) | |
Bodies: a selected sheet metal body, else the largest visible sheet metal body (warned); non-sheet-metal bodies are rejected.
Highlighting is via Fusion selection (not custom graphics).


# Phase 2 limitations
- **Manufacturer data**: only SendCutSend is substantially populated; PCBWay and Xometry could not be retrieved and produce NEEDS_REVIEW only. Hole-to-edge and feature
  spacing are unpublished/unverified for SendCutSend, so its best verdict is "conditionally compatible". See [MANUFACTURERS.md](MANUFACTURERS.md).
- **Cutouts**: slots (2 parallel lines + 2 half-circles), rectangles (incl. rounded corners) are measured; every other outline is "irregular" with an unknown narrowest width
  (size rules -> NEEDS_REVIEW). Non-through loops (pockets/embosses) are ignored by design, which could hide a cosmetic through-cut that is intentional — logged per face.
  A through-cut test uses adjoining wall height ≈ thickness; walls that cannot be measured give "through-cut not confirmed" (NEEDS_REVIEW).
- **Edge distance** is to the sheet's *outer* boundary only (other holes/cutouts are not counted); hole-to-hole and cutout-to-cutout spacing are not checked.
- **Assemblies**: visible sheet metal bodies in visible occurrences; instances of one component are analysed once (`instance_count`). Parts hidden, in unloaded/referenced-but-unreadable
  components, or flagged non-sheet-metal are skipped (a warning counts skipped bodies). Rigid-transform assumption: distances are taken in assembly space.
- **Bend/flange**: flange apex length assumes a flat flange face and a single bend; multi-bend (intermediate) flanges are excluded. Hole-to-bend uses only bends adjacent to the hole's face.
- **Flat size** is the flat pattern's axis-aligned bounding box.
- **Reports** are saved to `~/FusionDFM/reports/` (no file dialog); HTML opens in the default browser.
- **Unit display**: lengths are shown in mm and inches together regardless of the Fusion document units.
- Not implemented (by design): any CAD modification, AI/LLM calls, non-sheet-metal processes (CNC, 3D printing), SOLIDWORKS.
