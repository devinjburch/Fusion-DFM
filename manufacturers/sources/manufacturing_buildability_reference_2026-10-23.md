# Manufacturing Buildability Knowledge Base — PCBWay + Xometry

Research snapshot: 2026-10-23. Offline reference for Claude and a Fusion 360 buildability add-in.

**READ FIRST:** These are published design tips and selected capabilities, NOT promises of acceptance, certification, or electrical performance. Do not extrapolate beyond stated process, material, tooling or stock. Do not automatically declare a part buildable just because it passes checks.

**Machine-readable companion files:** `pcbway_buildability_rules_v1.json` (existing 30 provisional entries) and `xometry_buildability_rules_v1.json` (21 entries from checked Xometry sources).


## Instructions for Claude / application implementation

1. Use the exact source URL stored per rule. Do not claim Claude visited the website.
2. Normalize measured CAD dimensions into the units each rule uses; never silently compare inches with mm.
3. Applicability gate: manufacturer, process, material family and special geometry. If unknown, mark **NOT_EVALUATED** rather than pass/fail.
4. Classification: **ERROR** only if clearly verified as a hard restriction; **WARNING** for published recommendations; **REVIEW** for ambiguous dimensions/tooling/limitations; **INFO** for equations.
5. Preserve source prose and dimension datum definitions. Minimum hole-edge clearance differs from hole-center distance; do not conflate.
6. Evaluate each bend / each feature, highlight offending Fusion CAD entities, and report actual, target, units, and source.
7. Sheet stock limits are raw stock, not maximum finished part dimensions. Account for blank size, nesting margins and orientation.
8. Compare manufacturers side by side. Never transfer one manufacturer’s minimum radius to another as a verified rule.
9. Add regression tests around thicknesses 0.059 in, 0.085 in, 0.187 in and 0.250 in, including copper and steel.
10. Exclude busbar ampacity, heat rise, fault-current withstand, UL listing, dielectric clearances and coating specification from generic DFM pass/fail. Require qualified engineering review.


## PCBWay: extracted provisional rules (30)

Data source: original companion JSON from the earlier extraction. Individual entries should be treated as **provisional** pending check against primary pages. Recheck all numeric threshold interpretations before using hard-fail severity.

- **PCB-BEND-001** | bending | `minimum_finished_part_dimension_mm` >= `3` mm | severity `review`. Minimum finished part 3 by 3 mm; evaluate each planar dimension Source: https://www.pcbway.com/blog/Sheet_Metal/Sheet_Metal_Bending_Design_Guidelines_cbefb6cf.html
- **PCB-BEND-002** | bending | `flange_length_mm` >= `4 * thickness_mm` mm | severity `warning`. Standard minimum bend height; smaller may be possible under special conditions Source: https://www.pcbway.com/blog/Sheet_Metal/Sheet_Metal_Bending_Design_Guidelines_cbefb6cf.html
- **PCB-BEND-003** | bending | `inside_bend_radius_mm` manual_review `None` mm | severity `review`. Depends on material grade, temper, thickness, grain orientation and tooling; do not use universal R>=T Source: https://www.pcbway.com/blog/Sheet_Metal/Sheet_Metal_Bending_Design_Guidelines_cbefb6cf.html
- **PCB-BEND-004** | bending | `feature_to_bend_line_clearance_mm` >= `2 * thickness_mm` mm | severity `warning`. Initial bend-line clearance guideline; measure from feature boundary and review bend tangent geometry Source: https://www.pcbway.com/blog/Sheet_Metal/Sheet_Metal_Bending_Design_Guidelines_cbefb6cf.html
- **PCB-BEND-005** | bending | `bend_allowance_mm` formula `pi*(inside_radius_mm + k_factor*thickness_mm)*bend_angle_deg/180` mm | severity `info`. Flat pattern calculation, not a pass/fail threshold Source: https://www.pcbway.com/blog/Sheet_Metal/Sheet_Metal_Bending_Design_Guidelines_cbefb6cf.html
- **PCB-SHEET-STEEL** | stock | `flat_pattern_envelope_mm` fits_rectangle `[1500, 3000]` mm | severity `review`. Published raw-stock maximum; allows 90 degree rotation and requires 5mm margin each side for cutting Source: https://www.pcbway.com/blog/Sheet_Metal/Sheet_Metal_Bending_Design_Guidelines_cbefb6cf.html
- **PCB-SHEET-STAINLESS_STEEL** | stock | `flat_pattern_envelope_mm` fits_rectangle `[1500, 3000]` mm | severity `review`. Published raw-stock maximum; allows 90 degree rotation and requires 5mm margin each side for cutting Source: https://www.pcbway.com/blog/Sheet_Metal/Sheet_Metal_Bending_Design_Guidelines_cbefb6cf.html
- **PCB-SHEET-ALUMINUM** | stock | `flat_pattern_envelope_mm` fits_rectangle `[1220, 2440]` mm | severity `review`. Published raw-stock maximum; allows 90 degree rotation and requires 5mm margin each side for cutting Source: https://www.pcbway.com/blog/Sheet_Metal/Sheet_Metal_Bending_Design_Guidelines_cbefb6cf.html
- **PCB-SHEET-TITANIUM** | stock | `flat_pattern_envelope_mm` fits_rectangle `[1220, 2440]` mm | severity `review`. Published raw-stock maximum; allows 90 degree rotation and requires 5mm margin each side for cutting Source: https://www.pcbway.com/blog/Sheet_Metal/Sheet_Metal_Bending_Design_Guidelines_cbefb6cf.html
- **PCB-SHEET-COPPER** | stock | `flat_pattern_envelope_mm` fits_rectangle `[600, 1500]` mm | severity `review`. Published raw-stock maximum; allows 90 degree rotation and requires 5mm margin each side for cutting Source: https://www.pcbway.com/blog/Sheet_Metal/Sheet_Metal_Bending_Design_Guidelines_cbefb6cf.html
- **PCB-STOCK-EDGE** | stock | `nesting_margin_mm` >= `5` mm | severity `review`. Per sheet edge when cutting stock Source: https://www.pcbway.com/blog/Sheet_Metal/Sheet_Metal_Bending_Design_Guidelines_cbefb6cf.html
- **PCB-BEND-006** | bending | `bend_angle_deg` manual_review `None` degrees | severity `review`. Special/near-flat angles and tooling access require process interpretation; article cites bends below 5 degrees and included angles exceeding 130 degrees Source: https://www.pcbway.com/blog/Sheet_Metal/Sheet_Metal_Bending_Design_Guidelines_cbefb6cf.html
- **PCB-FORM-001** | bending | `flange_support_coverage_fraction` >= `1.0` ratio | severity `review`. For 0.187 or 0.250 inch sheet: both flanges require full bend-length support Source: https://www.pcbway.com/blog/Sheet_Metal/Sheet_Metal_Bending_DFM_Guide_to_Prevent_Warping_Tearing_and_Bending_Deformation_5c476b7f.html
- **PCB-CUT-001** | file_validation | `solid_body_count` == `1` count | severity `error`. For formed sheet STEP submissions; not a universal CNC assembly rule Source: https://www.pcbway.com/blog/Sheet-Cutting/Sheet_Cutting_Design_Guidelines_b0e8981b.html
- **PCB-CUT-002** | file_validation | `is_closed_profile` == `True` bool | severity `error`. 2D cutting profiles should form closed outlines Source: https://www.pcbway.com/blog/Sheet-Cutting/Sheet_Cutting_Design_Guidelines_b0e8981b.html
- **PCB-CUT-003** | file_validation | `has_duplicate_cut_edges` == `False` bool | severity `error`. Duplicate and overlapping lines can cause duplicate cutting Source: https://www.pcbway.com/blog/Sheet-Cutting/Sheet_Cutting_Design_Guidelines_b0e8981b.html
- **PCB-CUT-004** | file_validation | `has_pre_nested_3d_parts` == `False` bool | severity `error`. 3D STEP, IGES, SLDPRT assemblies should be uploaded as individual parts Source: https://www.pcbway.com/blog/Sheet-Cutting/Sheet_Cutting_Design_Guidelines_b0e8981b.html
- **PCB-CUT-005** | cnc_routing | `min_part_dimension_mm` >= `2` mm | severity `review`. General CNC routing minimum; specific material constraints vary Source: https://www.pcbway.com/blog/Sheet-Cutting/Sheet_Cutting_Design_Guidelines_b0e8981b.html
- **PCB-CUT-006** | cnc_routing | `max_part_dimension_mm` <= `1000` mm | severity `review`. General CNC routing upper dimension; engineer review may differ Source: https://www.pcbway.com/blog/Sheet-Cutting/Sheet_Cutting_Design_Guidelines_b0e8981b.html
- **PCB-CUT-007** | cnc_routing | `minimum_diameter_mm` >= `0.3` mm | severity `review`. General CNC routing diameter lower bound; process-specific Source: https://www.pcbway.com/blog/Sheet-Cutting/Sheet_Cutting_Design_Guidelines_b0e8981b.html
- **PCB-CUT-008** | cnc_routing | `internal_corner_radius_in` >= `0.063` in | severity `warning`. Routed internal corners cannot be sharp; depends on bit size Source: https://www.pcbway.com/blog/Sheet-Cutting/Sheet_Cutting_Design_Guidelines_b0e8981b.html
- **PCB-CUT-009** | cnc_routing | `dogbone_diameter_in` >= `tool_bit_diameter_in + 0.005` in | severity `warning`. For dogbone relief on square mating pockets Source: https://www.pcbway.com/blog/Sheet-Cutting/Sheet_Cutting_Design_Guidelines_b0e8981b.html
- **PCB-CUT-010** | cnc_routing | `perforation_removed_area_fraction` <= `0.5` ratio | severity `warning`. Flatbed routing skeletal or perforated parts Source: https://www.pcbway.com/blog/Sheet-Cutting/Sheet_Cutting_Design_Guidelines_b0e8981b.html
- **PCB-CUT-011** | cnc_routing | `tab_placement_vertex_spacing_in` >= `0.4` in | severity `review`. Minimum edge span for holding tab placement Source: https://www.pcbway.com/blog/Sheet-Cutting/Sheet_Cutting_Design_Guidelines_b0e8981b.html
- **PCB-HW-001** | hardware | `hole_center_to_edge_mm` >= `1.5 * mounting_hole_diameter_mm` mm | severity `warning`. General rule of thumb; override with exact hardware manufacturer specs Source: https://www.pcbway.com/blog/Hardware-insertion/Hardware_Installation_Design_Guidelines_15aa42f5.html
- **PCB-HW-002** | hardware | `hole_center_to_edge_mm` >= `2 * mounting_hole_diameter_mm` mm | severity `advisory`. Preferred high load / thin sheet condition Source: https://www.pcbway.com/blog/Hardware-insertion/Hardware_Installation_Design_Guidelines_15aa42f5.html
- **PCB-HW-003** | hardware | `adjacent_same_hardware_center_spacing_mm` >= `3 * mounting_hole_diameter_mm` mm | severity `warning`. Same fastener family; actual tooling envelope may govern Source: https://www.pcbway.com/blog/Hardware-insertion/Hardware_Installation_Design_Guidelines_15aa42f5.html
- **PCB-HW-004** | hardware | `hardware_center_to_bend_tangent_mm` >= `inside_radius_mm + thickness_mm + hardware_margin_mm` mm | severity `warning`. Margin must be determined from hardware flange and tooling Source: https://www.pcbway.com/blog/Hardware-insertion/Hardware_Installation_Design_Guidelines_15aa42f5.html
- **PCB-HW-005** | hardware | `hardware_center_to_bend_line_mm` >= `2*thickness_mm + inside_radius_mm + 3` mm | severity `advisory`. Alternative published typical clearance, uses millimeters Source: https://www.pcbway.com/blog/Hardware-insertion/Hardware_Installation_Design_Guidelines_15aa42f5.html
- **PCB-HW-006** | hardware | `hardware_compatibility` manual_review `None` None | severity `review`. Check fastener hardness, sheet hardness and manufacturer part datasheet Source: https://www.pcbway.com/blog/Hardware-insertion/Hardware_Installation_Design_Guidelines_15aa42f5.html

## PCBWay: additional verified interpretation notes

- Published bending guide (2026-09-04): finished part minimum 3 × 3 mm; stock max steel/stainless 1500 × 3000 mm, aluminum/titanium 1220 × 2440 mm, copper 600 × 1500 mm; sheet-cutting margin 5 mm per edge.
- General bend height: approximately 4 × thickness; 3 mm can be possible for t ≤ 1 mm with appropriate tooling. Treat as warning/review.
- Hole/cutout near bend: initial evaluation distance ≥2 × thickness **from actual hole/cutout edge to bend line**. Larger clearance may be needed.
- Minimum radius: PCBWay explicitly states material/thickness/temper/grain/tooling dependent. Do NOT impose universal 1× thickness as a hard PCBWay limit.
- Separate PCBWay article states minimum flange = inside bend radius + 4T; this is stricter than the general 4T bend-height guidance. Preserve as a distinct source and flag ambiguity instead of silently choosing.
- PCBWay forming guide calls for continuous minimum flange support over full bend length in 0.187 and 0.250 inch material.
- Standard press brake bend features may need manual review for tooling interference and exotic forming.

Sources:
- https://www.pcbway.com/blog/Sheet_Metal/Sheet_Metal_Bending_Design_Guidelines_cbefb6cf.html
- https://www.pcbway.com/blog/PCB_Design_Layout/Sheet_Metal_Bending_Design_Guide_DFM_Rules_Bend_Radius_Bend_Allowance_and_Ma_cd445f27.html
- https://www.pcbway.com/blog/Sheet_Metal/Sheet_Metal_Bending_DFM_Guide_to_Prevent_Warping_Tearing_and_Bending_Deformation_5c476b7f.html
- https://www.pcbway.com/rapid-prototyping/Sheet-metal/bending.html

## Xometry: directly transcribed numeric rule registry (21)

- **XOM-SM-001** | `minimum_inside_bend_radius` >= `1` times_material_thickness | WARNING. Interpret minimum bend 1X MT as radius recommendation; confirm specific material and tooling. Source: https://www.xometry.com/capabilities/sheet-metal-fabrication/
- **XOM-SM-002** | `hole_edge_to_part_edge` >= `2` times_material_thickness | WARNING. Measurement edge-to-edge; see published feature names. Source: https://www.xometry.com/capabilities/sheet-metal-fabrication/
- **XOM-SM-003** | `hole_to_hole_spacing` >= `6` times_material_thickness | REVIEW. Publisher does not clarify whether center-to-center or edge-to-edge; do not automate until resolved. Source: https://www.xometry.com/capabilities/sheet-metal-fabrication/
- **XOM-SM-004** | `bend_edge_to_hole_spacing` >= `6` times_material_thickness | REVIEW. Bend edge datum ambiguous; manual verification needed. Source: https://www.xometry.com/capabilities/sheet-metal-fabrication/
- **XOM-SM-005** | `feature_to_countersink` >= `8` times_material_thickness | REVIEW. Feature datum ambiguous; manual verification needed. Source: https://www.xometry.com/capabilities/sheet-metal-fabrication/
- **XOM-SM-006** | `minimum_countersink_depth` >= `0.6` times_material_thickness | WARNING. Check suitability for thickness and screw design. Source: https://www.xometry.com/capabilities/sheet-metal-fabrication/
- **XOM-SM-007** | `relief_cuts` >= `1` times_material_thickness | REVIEW. Clarify relief width versus depth before automatic checking. Source: https://www.xometry.com/capabilities/sheet-metal-fabrication/
- **XOM-SM-008** | `corner_fillet_radius` >= `0.5` times_material_thickness | WARNING. Clarify corner fillet geometry before automatic checking. Source: https://www.xometry.com/capabilities/sheet-metal-fabrication/
- **XOM-CAP-001** | `typical_sheet_thickness_min` >= `0.024` in | REVIEW. Typical; thinner available by review Source: https://www.xometry.com/capabilities/sheet-metal-fabrication/
- **XOM-CAP-002** | `typical_sheet_thickness_max` <= `0.25` in | REVIEW. Typical; thicker available by review Source: https://www.xometry.com/capabilities/sheet-metal-fabrication/
- **XOM-CAP-003** | `blank_short_side_max` <= `60` in | REVIEW. Nominal 5 x 10 ft blank, larger upon request Source: https://www.xometry.com/capabilities/sheet-metal-fabrication/
- **XOM-CAP-004** | `blank_long_side_max` <= `120` in | REVIEW. Nominal 5 x 10 ft blank, larger upon request Source: https://www.xometry.com/capabilities/sheet-metal-fabrication/
- **XOM-CAP-005** | `automatic_quoted_tolerance` >= `0.005` in | REVIEW. As tight as ±.005 inch for some dimensions; tighter requires manual review Source: https://www.xometry.com/capabilities/sheet-metal-fabrication/
- **XOM-CNC-001** | `minimum_metal_wall` >= `0.794` mm | WARNING. Design recommendation Source: https://www.xometry.com/resources/machining/10-tips-improve-cad-cnc-design/
- **XOM-CNC-002** | `minimum_plastic_wall` >= `1.5` mm | WARNING. Design recommendation Source: https://www.xometry.com/resources/machining/10-tips-improve-cad-cnc-design/
- **XOM-CNC-003** | `cavity_depth_width_ratio` <= `5` ratio | WARNING. 3–5 recommended; deeper may need review Source: https://www.xometry.com/resources/machining/10-tips-improve-cad-cnc-design/
- **XOM-CNC-004** | `internal_corner_radius_to_tool_radius` >= `1.3` ratio | WARNING. Rule of thumb, not guaranteed machining limit Source: https://www.xometry.com/resources/machining/10-tips-improve-cad-cnc-design/
- **XOM-CNC-005** | `recommended_thread_depth_diameter_ratio` <= `2` ratio | WARNING. Cost guidance; typically 1.5–2x diameter Source: https://www.xometry.com/resources/machining/10-tips-improve-cad-cnc-design/
- **XOM-CNC-006** | `blind_hole_unthreaded_bottom` >= `0.5` times_diameter | WARNING. Additional length recommendation Source: https://www.xometry.com/resources/machining/10-tips-improve-cad-cnc-design/
- **XOM-CNC-007** | `feature_size` >= `2.5` mm | WARNING. Common tool size; smaller possible with special tools Source: https://www.xometry.com/resources/machining/10-tips-improve-cad-cnc-design/
- **XOM-CNC-008** | `recommended_drilled_hole_depth_diameter` <= `4` ratio | WARNING. Up to 10x possible but costly Source: https://www.xometry.com/resources/machining/10-tips-improve-cad-cnc-design/

## Example evaluation: 0.187 inch copper sheet

Thickness = 4.7498 mm. The following are arithmetic consequences of published multipliers, **not manufacturer approval**.
- PCBWay 4T bend-height starting guidance: 0.748 in (19.0 mm). The distinct R+4T guide would need added radius.
- PCBWay 2T hole-edge-to-bend-line starting clearance: 0.374 in (9.5 mm).
- Xometry 1T minimum-bend recommendation: 0.187 in (4.75 mm), subject to copper temper/tooling.
- Xometry 2T hole-to-edge distance: 0.374 in (9.5 mm).
- Xometry 6T hole-to-hole: 1.122 in (28.5 mm); **do not apply until datum (center/edge) verified**.
- Xometry nominal 0.024–0.250 in sheet thickness range encompasses 0.187 in; quote and material selection still required.

## Unknowns and follow-up research

- Full Xometry downloadable PDFs were not acquired; only publicly readable webpages and their numeric tables were used.
- PCBWay existing JSON includes rules for hardware, CNC routing, stock and files; manually verify each before marking production-ready.
- Actual cutting kerfs, laser limits for reflective copper, countersink/counterbore suitability, tab/notch datum, PEM fit specifications, material-specific bend minimums, and supplier plating availability require deeper official verification.
- For electrical busbars and breaker hardware: manufacturing geometry does not validate electrical safety or replacement equivalence.

## Machine-readable response contract for Fusion add-in

Suggested output per checked feature:
```json
{
  "manufacturer": "Xometry",
  "rule_id": "XOM-SM-002",
  "result": "WARNING",
  "feature_id": "face_or_edge_token",
  "actual_mm": 4.0,
  "required_mm": 9.5,
  "source_url": "https://www.xometry.com/capabilities/sheet-metal-fabrication/",
  "reason": "Hole-to-edge guidance: 2x material thickness",
  "confidence": "published_recommendation"
}
```
