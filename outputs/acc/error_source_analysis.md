# ACC Tool Error Source Analysis — Test Models

This document analyses the root causes of errors (FP and FN) for each failing rule
on the 4 test models: 4351, digital_hub, samuel_macalister_sample_house, wbdg_office.

Ground truth uses the `extraction_element` approach: only GUIDs matching the expected
IFC type per rule are considered (e.g. only IfcSlab for slab rules, only IfcDoor for
door rules).

---

## Error Source Categories

| ID | Category | Description |
|----|----------|-------------|
| **E1** | Property lookup failure | Tool cannot find the relevant property due to non-standard pset names, missing data, or language differences |
| **E2** | Relationship traversal gap | Tool relies on IFC relationships (e.g. IfcRelSpaceBoundary) that are incomplete in certain models |
| **E3** | Geometry approximation error | Bounding box, convex hull, or sampling-based geometry checks are too coarse |
| **E4** | Missing rule logic | Tool lacks part of the rule (e.g. doesn't handle certain subtypes, missing sub-rules) |
| **E5** | Threshold / tolerance mismatch | Tool uses different thresholds than Solibri |
| **E6** | Model-specific IFC structure | Model uses non-standard structuring that breaks tool assumptions |

---

## Perfect Rules (F1 = 1.000)

### circular_space, stair_slab_connection, same_storey_elevation, doors_and_windows

These 4 rules achieve perfect F1 on all test models:

- `circular_space`: single geometric measurement (inscribed circle diameter)
- `stair_slab_connection`: geometric collision detection between stairs and slabs
- `same_storey_elevation`: property comparison (bottom elevation equality)
- `doors_and_windows`: floor-level comparison + orphan detection via IFC relationships (F1=1.0, 18 TP)

No errors to analyse.

---

## Per-Rule Error Analysis

### 1. slab_thickness — F1=0.000 (FP=0, FN=3) --- Confirmed

**All 3 FN are IfcSlab in digital_hub.** Slabs with Thickness = 0.00m.

**Root cause: E1 — Property lookup failure.**
The digital_hub model is German — the property is named "Dicke" not "Thickness".
The tool searches for `Thickness` in any pset and skips elements where it's not found.
A slab with no recognisable thickness property is silently skipped rather than flagged.

---

### 2. 504_2_riser_height — F1=0.462 (TP=3, FP=7, FN=0)

- MacCallister has 180.55555555556 - likely some thresholds/tolerances need to be adjusted; Pset_StairCommon --- No, missing unit conversion
- 4351 has 0.55 --- measurements considered? -- Pset_StairCommon.RiserHeight = 0.55m, but max riser height from revit is correct - 0.18.

**All elements are IfcStair.** All violations are caught (FN=0) but 7 stairs are over-flagged (FP=7): 3 in 4351, 2 in digital_hub, 2 in samuel_macalister.

**Root cause: E5 — Threshold mismatch.** Stairs flagged by the tool are compliant
per Solibri. The tool reads nominal `Pset_StairCommon.RiserHeight`, while Solibri
measures actual geometry or applies different tolerances.

---

### 3. 504_2_tread_length — F1=0.667 (TP=2, FP=2, FN=0)

--- Different measurements used by Solibri

**All elements are IfcStair.** 2 FP in digital_hub.

**Root cause: E5 — Threshold mismatch.**
The tool returns stairs whose `TreadLength` < 0.28m. The 2 FP stairs are flagged by
the tool but not by Solibri — likely borderline cases where the measured vs. nominal
tread length differs, or the tool reads from a different property source.

---

### 4. 504_2_non_uniform_risers_treads — F1=0.000 (FP=5, FN=0)

---- Heuristic didn't work well, need to look at the data more closely. The tool checks if all risers/treads in a stair are the same by comparing their nominal properties, but it doesn't detect variations within a stair. -- I'd change to geometry/rule

**All 5 FP are IfcStair.** No expected violations on test models (ground truth = 0).

**Root cause: E3 — Geometry approximation error.**
The tool's uniformity detection (comparing individual riser heights within a flight)
is more sensitive than Solibri's tolerance. Needs a geometry-based approach rather
than property comparison.

---

### 5. clearance_front_of_doors — F1=0.000 (FP=0, FN=11)

**All 11 FN are IfcDoor** across all 4 models (2 in 4351, 6 in digital_hub,
2 in samuel_macalister, 1 in wbdg_office). The tool returns no results on any model.

**Root cause: E3 + E4 — Geometry approximation + missing rule logic.**
The tool is overly conservative — its clearance zone construction or intersection
check never triggers, returning an empty list on all models. The fundamental issue
remains: constructing a correctly-oriented clearance zone from door placement and
detecting genuine geometric obstruction is beyond what property-based or AABB
approaches can reliably do.

---

### 7. large_spaces_more_than_one_door — F1=0.267 (TP=4, FP=1, FN=21)

--- confirmed - Models have no IfcRelSpaceBoundary, so the tool can't count doors per space. The tool relies on `IfcRelSpaceBoundary` to navigate from Spaces to their bounding elements, i.e., walls. - More training models would help. Or export problem/missing relationships.

**All elements are IfcSpace.** High precision (0.80) but very low recall (0.16).

**FN root cause: E2 — Relationship traversal gap.**
21 spaces missed across all 4 models. The tool counts doors via `IfcRelSpaceBoundary`,
which is incomplete or absent in many models. Solibri uses geometric containment
instead. The digital_hub model (11 FN) is the worst — likely has poor/missing
`IfcRelSpaceBoundary` data.

---

### 8. slabs_guarded_against_falling — F1=0.286 (TP=3, FP=11, FN=4)

--- Seems geometry-based --- non optimised heuristic. Height from geometry rather than quantity/property.

**All elements are IfcSlab.** Better recall than before but worse precision:
TP=3, FP=11 (digital_hub: 5, samuel_macalister: 4, 4351: 1, wbdg_office: 1), FN=4.

**Root cause: E3 — Geometry approximation error.**
The heuristic is aggressive: it detects more unprotected slabs but also flags slabs
Solibri considers safe. The convex hull / perimeter sampling approach for barrier
footprints is too coarse. The barrier height computation (`top_z - bottom_z` of the
entire element, not relative to slab top) doesn't robustly detect low or missing
barriers.

---

### 9. space_validation_inside — F1=0.273 (TP=3, FP=2, FN=14)

--- Geometry checks too restrictive + Solibri parameters not described enough. Multiple sub-rules in one rule.

Check Bottom Surface: True" in SOL/202 (Space Validation) means: the bottom surface of each space must touch a slab or another space below it. If no slab is found beneath the space, it gets flagged.

**All elements are IfcSpace.** Good precision but low recall. 2 FP in wbdg_office;
14 FN mostly in digital_hub stairwells (9) and wbdg_office restrooms (4).

**Root cause: E3 — Geometry approximation + E4 — Missing sub-rule.**
The tool checks if ALL vertices of a component are inside the space mesh (`np.all(contains)`),
which is too strict — any element with a protruding vertex is not flagged. Additionally,
the ground truth flags spaces where no slab/roof/space surface is below (sub-rule not
implemented). The 4 FN restroom spaces in wbdg_office are from this missing sub-rule.

---

### 10. space_validation_intersect — F1=0.458 (TP=22, FP=52, FN=0)

--- Geometry check too restrictive

**All elements are IfcSpace.** All violations are caught (FN=0) but FP=52 —
digital_hub (21), wbdg_office (27), 4351 (3), samuel_macalister (1).

**Root cause: E3 — Geometry approximation error.**
The tool uses `clash_intersection_many` with 0.03m tolerance and excludes
fully-contained elements. The large FP count indicates the tool detects intersections
Solibri considers acceptable (e.g. construction tolerances, shared boundaries).

---

### 11. 305_3_size — F1=0.000 (FP=2, FN=1)

-- heuristic used for checking - rotating bounding box and checking every 5 degrees.

**1 FN: IfcSpace in samuel_macalister** (Master Bedroom with inaccessible areas).
**2 FP: IfcSpace in digital_hub** — two spaces incorrectly flagged as too small.

**Root cause: E3 — Geometry approximation.**
The tool uses random sampling (Monte Carlo) to check if a 760×1220mm rectangle fits.
This approach is non-deterministic and unreliable for complex geometries — the 2 FP
in digital_hub likely result from sampling variation.

---

### 12. 404_2_5_two_doors_in_series — F1=0.000 (FP=0, FN=2)

----- confirmed - Models have no IfcRelSpaceBoundary, so the tool can't count doors per space. The tool relies on `IfcRelSpaceBoundary` to navigate from Spaces to their bounding elements, i.e., walls. - More training models would help. Or export problem/missing relationships.

**2 FN: IfcDoor in samuel_macalister.** Distance between doors is 1.16m (min = 1.22m).

**Root cause: E2 — Relationship traversal gap.**
The tool pairs doors in circulation spaces via `IfcRelSpaceBoundary`. The model
likely lacks this relationship for the relevant space, so the doors weren't paired.

---

### 13. unallocated_areas — F1=0.000 (FP=8, FN=20)

--- Geometry-based heuristic

**FP types: IfcWall / IfcWallStandardCase.** 8 FP across 4351 (5) and wbdg_office (3).
**FN types: IfcWall, IfcWallStandardCase, IfcCurtainWall, IfcColumn** — 20 across all models.

**Root cause: E3 — Geometry approximation.**
The tool constructs wall buffers from centrelines (0.2m buffer), subtracts space
footprints, then returns surrounding wall GUIDs. Fundamentally fragile:

1. Wall centreline extraction uses the longest polygon edge — poor for non-rectangular walls
2. The 0.2m buffer doesn't match actual wall thickness
3. The ground truth expects specific surrounding wall GUIDs per unallocated area — even small geometry differences change which walls are "surrounding"

The FN include IfcCurtainWall and IfcColumn elements that the wall-buffer approach
doesn't detect as boundaries of unallocated areas.

---

## Summary of Error Sources

Global test performance: **F1=0.688** (TP=183, FP=90, FN=76)

Total errors across 12 failing rules: **FP=90, FN=76**

| Error Source | Rules Affected | Total FP | Total FN |
|---|---|---|---|
| **E3: Geometry-based heuristic** | clearance_doors, slabs_guarded, space_inside, space_intersect, non_uniform, 305_3, unallocated | 73 | 30 |
| **E2: Relationship traversal gap** | large_spaces, 404_2_5 | 1 | 23 |
| **E4: Missing rule logic / sub-rules** | clearance_doors, space_inside | 0 | 15 |
| **E1: Property lookup / unit conversion** | slab_thickness | 0 | 3 |
| **E5: Threshold / tolerance mismatch** | riser_height, tread_length | 9 | 0 |
| **E6: Model-specific IFC structure** | — | 0 | 0 |

**Key findings:**

1. **Geometry-based heuristics (E3)** are the dominant error source, accounting for 81%
   of FPs and 39% of FNs. Tools use coarse approximations (bounding boxes, convex hulls,
   random sampling) that don't match Solibri's precise geometry engine.

2. **Missing IFC relationships (E2)** account for 30% of FNs. Models without
   `IfcRelSpaceBoundary` force the tool to rely on geometry, which it can't do well.
   More diverse training models or fallback to geometric door-counting would help.

3. **Property/unit issues (E1)** affect multilingual models (German "Dicke" vs English
   "Thickness") and models with inconsistent unit conventions. Only slab_thickness (3 FN)
   remains affected.

4. **4 rules achieve perfect F1=1.0** on test (circular_space, stair_slab_connection,
   same_storey_elevation, doors_and_windows). These succeed because they use unambiguous
   logic: single property comparisons, direct collision detection, or well-defined IFC
   relationships.
