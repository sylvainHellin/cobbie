# ACC Tool Error Source Analysis — Test Models (V2 Ground Truth)

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

### circular_space, stair_slab_connection, same_storey_elevation

These 3 rules achieve perfect F1 on all test models. Their logic is unambiguous:
- `circular_space`: single geometric measurement (inscribed circle diameter)
- `stair_slab_connection`: geometric collision detection between stairs and slabs
- `same_storey_elevation`: property comparison (bottom elevation equality)

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

### 2. 504_2_riser_height — F1=0.222 (TP=1, FP=5, FN=2) 

- MacCallister has 180.55555555556 - likely some thresholds/tolerances need to be adjusted; Pset_StairCommon --- No, missing unit conversion
- 4351 has 0.55 --- measurements considered? -- Pset_StairCommon.RiserHeight = 0.55m, but max riser height from revit is correct - 0.18. 

**All FP and FN are IfcStair.** V2 ground truth correctly expects only stair GUIDs.

**FP (5 IfcStair):** 3 in 4351, 2 in samuel_macalister. The tool flags stairs whose
`Pset_StairCommon.RiserHeight` falls outside 100–180mm, but these stairs are compliant
according to Solibri. Likely cause: **E5 — Threshold mismatch.** The tool reads a
nominal riser height from properties, while Solibri may measure actual geometry or
use a different tolerance.

**FN (2 IfcStair in digital_hub):** Stairs with non-uniform risers (329mm at beginning,
180mm elsewhere). The tool only checks the nominal `RiserHeight` property, which may
report the standard height (180mm = compliant). **E4 — Missing rule logic:** the tool
doesn't detect non-uniform risers within a single stair.

---

### 3. 504_2_tread_length — F1=0.667 (TP=2, FP=2, FN=0)

--- Different measurements used be Solibri

**All elements are IfcStair.** 2 FP in digital_hub.

**Root cause: E5 — Threshold mismatch.**
The tool returns stairs whose `TreadLength` < 0.28m. The 2 FP stairs are flagged by
the tool but not by Solibri — likely borderline cases where the measured vs. nominal
tread length differs, or the tool reads from a different property source.

---

### 4. 504_2_non_uniform_risers_treads — F1=0.000 (FP=5, FN=0)

---- Heuristic didn't work well, need to look at the data more closely. The tool checks if all risers/treads in a stair are the same by comparing their nominal properties, but it doesn't detect variations within a stair. -- I'd change to geometry/rule

**All 5 FP are IfcStair.** No expected violations on test models (ground truth = 0).

**Root cause: E5 — Threshold/tolerance mismatch.**
The tool flags 5 stairs as having non-uniform risers/treads when they should be
compliant. The tool's uniformity detection (comparing individual riser heights
within a flight) is more sensitive than Solibri's tolerance.

---

### 5. clearance_front_of_doors — F1=0.112 (TP=5, FP=73, FN=6)

--- Classify just as geometry?

**All elements are IfcDoor.** Massive FP count (73), mostly in digital_hub (29) and
wbdg_office (43).

**FP root cause: E3 — Geometry approximation error.**
The tool creates a clearance zone box from the door's local placement and checks
bounding box intersection with all building elements. This is far too coarse:
1. The clearance zone direction may not correspond to the actual swing side
2. Bounding box intersection over-reports — any element whose AABB overlaps counts
3. The clearance zone Z-range is hard-coded, ignoring actual door elevation

The 73 FPs mean the tool flags almost every door in larger models.

**FN root cause (6 IfcDoor): E3 + E4.**
Missed doors where components (slabs, walls, sanitary terminals) intersect the
clearance area. The tool may project the clearance zone in the wrong direction,
or the intersecting component's bounding box doesn't overlap despite actual
geometric interference.

---

### 6. doors_and_windows — F1=0.250 (TP=2, FP=12, FN=0)

**TP: 2 IfcWindow. FP: 8 IfcWindow + 4 IfcDoor.**

**Root cause: E4 — Missing rule logic + E6 — Model-specific structure.**
The tool checks if doors/windows are on a different floor than their host wall.
The 12 FPs are elements flagged as mismatched but considered compliant by Solibri.
Likely causes:
- Doors/windows spanning storey boundaries are legitimate
- `get_container()` returns a different storey than expected for some elements
- Elements without a spatial container are incorrectly flagged

---

### 7. large_spaces_more_than_one_door — F1=0.267 (TP=4, FP=1, FN=21)

**All elements are IfcSpace.** High precision (0.80) but very low recall (0.16).

**FN root cause: E2 — Relationship traversal gap.**
21 spaces missed across all 4 models. All FN descriptions say "Count (0) of
components does not match requirement >= 2" — the tool found 0 doors for these
spaces. The tool counts doors via `IfcRelSpaceBoundary`, which is incomplete or
absent in many models. Solibri uses geometric containment instead.

The digital_hub model (11 FN) is the worst — likely has poor/missing
`IfcRelSpaceBoundary` data.

---

### 8. slabs_guarded_against_falling — F1=0.167 (TP=1, FP=4, FN=6)

**All elements are IfcSlab.** V2 ground truth dramatically simplified this rule
(was 58 FN with V1, now 6 FN) by only expecting slab GUIDs, not barrier GUIDs.

**FP (4 IfcSlab):** Slabs flagged as unprotected but considered safe by Solibri.
**E3 — Geometry approximation:** convex hull for barrier footprints over- or
under-estimates coverage. The tool's perimeter sampling (every 0.05m) with 0.15m
gap tolerance may misjudge protection.

**FN (6 IfcSlab):** Slabs that should be flagged but aren't. 3 in
samuel_macalister (barriers too low or missing), 2 in 4351 (barriers too low at
0.91m vs required 1.0m), 1 in digital_hub. **E3 + E4:** barrier height is computed
as `top_z - bottom_z` of the entire element (not relative to slab top), and the
tool doesn't robustly detect "missing barrier" scenarios.

---

### 9. space_validation_inside — F1=0.300 (TP=3, FP=0, FN=14)

**All elements are IfcSpace.** Perfect precision but low recall.

**FN root cause: E3 — Geometry approximation + E4 — Missing sub-rule.**
The tool checks if ALL vertices of a component are inside the space mesh
(`np.all(contains)`). This is too strict — if even one vertex protrudes, the
component isn't flagged.

Additionally, the ground truth flags spaces where "Space doesn't touch slab, roof,
or space surface below itself" — a separate sub-rule the tool doesn't implement.
4 FN in wbdg_office are this sub-rule (restroom spaces).

---

### 10. space_validation_intersect — F1=0.444 (TP=20, FP=48, FN=2)

**All elements are IfcSpace.** High recall (0.91) but low precision (0.29).

**FP (48 IfcSpace):** 44 in digital_hub, 1 in 4351, 1 in samuel_macalister,
2 in wbdg_office. **E5 — Tolerance mismatch:** the tool uses
`clash_intersection_many` with 0.03m tolerance and excludes fully-contained
elements. The 44 FPs in digital_hub suggest the tool detects intersections
Solibri considers acceptable.

**FN (2 IfcSpace in 4351):** Spaces intersecting walls that weren't detected.
**E6 — Model-specific structure:** the geometry tree may not include all
relevant elements for this model.

---

### 11. 305_3_size — F1=0.000 (FP=0, FN=1)

**1 FN: IfcSpace in samuel_macalister** (Master Bedroom with inaccessible areas).

**Root cause: E3 — Geometry approximation.**
The tool uses random sampling (20 points) to check if a 760x1220mm rectangle fits.
This Monte Carlo approach is non-deterministic and may miss complex geometries.
The single FN space has inaccessible areas the sampling failed to detect.

---

### 12. 404_2_5_two_doors_in_series — F1=0.000 (FP=0, FN=2)

**2 FN: IfcDoor in samuel_macalister.** Distance between doors is 1.16m (min = 1.22m).

**Root cause: E2 — Relationship traversal gap.**
The tool pairs doors in circulation spaces via `IfcRelSpaceBoundary`. The model
likely lacks this relationship for the relevant space, so the doors weren't paired.
With V2 ground truth, both door GUIDs are now expected (was 1 with V1's
`context_and_primary` strategy).

---

### 13. unallocated_areas — F1=0.000 (FP=13, FN=20)

**FP types: 7 IfcWallStandardCase + 6 IfcWall.**
**FN types: 11 IfcWall + 4 IfcWallStandardCase + 4 IfcCurtainWall + 1 IfcColumn.**

**Root cause: E3 — Geometry approximation.**
The tool constructs wall buffers from centrelines (0.2m buffer), subtracts space
footprints, then returns surrounding wall GUIDs. This is fundamentally fragile:
1. Wall centreline extraction uses the longest polygon edge — poor for non-rectangular walls
2. The 0.2m buffer doesn't match actual wall thickness
3. The ground truth expects specific surrounding wall GUIDs per unallocated area —
   even small geometry differences change which walls are "surrounding"

The FN include IfcCurtainWall and IfcColumn elements that the tool's wall-buffer
approach doesn't detect as boundaries of unallocated areas.

---

## Summary of Error Sources

| Error Source | Rules Affected | Total FP | Total FN |
|---|---|---|---|
| **E3: Geometry approximation** | clearance_doors, slabs_guarded, space_inside, space_intersect, 305_3, unallocated | 125 | 23 |
| **E2: Relationship traversal** | large_spaces, 404_2_5 | 0 | 23 |
| **E5: Threshold/tolerance mismatch** | riser_height, tread_length, non_uniform, space_intersect | 12 | 0 |
| **E4: Missing rule logic** | clearance_doors, space_inside, riser_height, doors_windows | 0 | 12 |
| **E1: Property lookup failure** | slab_thickness | 0 | 3 |
| **E6: Model-specific structure** | doors_windows, space_intersect | 12 | 2 |

**Top error source:** Geometry approximation (E3) accounts for 77% of FPs and 30% of FNs.
Relationship traversal gaps (E2) account for 30% of FNs — these are models where
`IfcRelSpaceBoundary` is incomplete, forcing geometric approaches.
