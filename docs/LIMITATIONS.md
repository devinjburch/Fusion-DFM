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
