# ACC Tool Error Source Analysis — Test Models

This document analyses the root causes of errors (FP and FN) for each failing rule
on the 4 test models: 4351, digital_hub, samuel_macalister_sample_house, wbdg_office.

---

## Error Source Categories

We classify error sources into the following categories:

| ID | Category | Description |
|----|----------|-------------|
| **E1** | GUID strategy mismatch | Tool returns the wrong element type (e.g. stair GUID instead of sub-components, or space GUID instead of wall GUIDs) |
| **E2** | Over-inclusive element traversal | Tool adds decomposed sub-elements that aren't expected (railings, stringers, etc.), inflating FP count |
| **E3** | Property lookup failure | Tool cannot find the relevant property (thickness, riser height, etc.) due to non-standard pset names or missing data |
| **E4** | Relationship traversal gap | Tool uses IfcRelSpaceBoundary or similar relationships that are incomplete in certain models |
| **E5** | Geometry approximation error | Convex hull, bounding box, or sampling-based geometry checks are too coarse, causing FP or FN |
| **E6** | Threshold / parameter mismatch | Tool uses different thresholds than the ground truth checker (Solibri) |
| **E7** | Missing rule logic | Tool lacks part of the rule logic (e.g. doesn't check both sides of door, doesn't handle certain element subtypes) |
| **E8** | Model-specific IFC structure | IFC model uses non-standard structuring (e.g. no IfcRelSpaceBoundary, spaces without area properties) |

---

## Per-Rule Analysis

### 1. slab_thickness — F1=0.000 (FN=3, FP=0)

**Errors:** 3 FN in digital_hub (GUIDs: `3A8hY1UoD7JhnLeZeDyU2J`, `3LJODRGPbDdfXHXShFL93Z`, `3LJODRGPbDdfXHXShFL9C6`)

**Ground truth:** Slabs with Thickness = 0.00m (violates >= 0.03m minimum).

**Root cause: E3 — Property lookup failure.**
The tool searches for a `Thickness` key in any pset. The digital_hub model likely stores thickness in a quantity set (IfcElementQuantity) rather than a property set, or the property has a different name. Slabs with 0.00m thickness probably lack the `Thickness` property entirely, so the tool skips them (`thickness is None → continue`). The tool's fallback for missing data is to skip — but a slab with NO thickness property should arguably be flagged.

**Secondary: E7 — Missing rule logic.** The tool also excludes "Slab on Grade" by name matching, which could be overly aggressive depending on naming conventions.

SF: Digital_hub is German -> Dicke -> not Thickness

---

### 2. 504_2_riser_height — F1=0.051 (FP=34, FN=3)

**FP pattern (34 total):** Massive over-reporting across 4351 (17), digital_hub (8), samuel_macalister (9).

**FN pattern (3 total):** 3 missed in digital_hub — stair sub-components expected by ground truth.

**Root cause: E2 — Over-inclusive element traversal.**
The tool's `add_violating_stair_elements()` adds not just the stair itself, but ALL decomposed sub-elements (flights, railings, stringers, landings). The ground truth only expects the **stair GUID itself**, not the sub-elements. This is the primary driver of 34 FPs — each violating stair produces ~5-10 extra GUIDs.

**Secondary: E1 — GUID strategy mismatch for FN.**
The 3 FNs in digital_hub reference sub-component GUIDs (`0YVU7tDBX86u6UVVsSmdx$`, `23Np8uMAvEN9H6Ds49deXD`, `3LF03GdXv2GhSTK1xTZzXx`). The ground truth expects *specific* sub-component GUIDs (the stair flights with non-uniform risers), but the tool only adds them as part of bulk decomposition — it doesn't check individual flight riser heights separately.

---

### 3. 504_2_tread_length — F1=0.667 (FP=2, FN=0)

**FP pattern:** 2 FPs in digital_hub (`0YVU7tDBX86u6UVVsSmdx$`, `3LF03GdXv2GhSTK1xTZzXx`).

**Root cause: E1 — GUID strategy mismatch.**
The tool returns **stair GUIDs** (IfcStair), but the ground truth expects the specific **IfcStairFlight GUIDs** that have the short treads. The 2 FP GUIDs are stair flights that the ground truth doesn't flag for tread length (they may have acceptable tread length but were returned because their parent stair was flagged).

Actually, re-checking: the tool returns stair GUIDs only. The 2 FPs are likely IfcStair GUIDs where the ground truth expects IfcStairFlight GUIDs. The tool doesn't distinguish between the stair and its flights.

---

### 4. 504_2_stair_slab_connection — F1=0.571 (FP=0, FN=3)

**FN pattern:** 3 missed stairs in wbdg_office (`1Cckmc_QjEFAHHQ3e8qDFi`, `27dLDsxMX8Sv5rKurGZypo`, `37hauuzqP2MBAzwN0mWNjY`).

**Root cause: E5 — Geometry approximation error.**
The tool uses `tree.clash_collision_many()` with `allow_touching=True` to detect stair-slab connections. If the stair geometry doesn't physically touch/overlap the slab geometry (e.g. there's a small gap between the stair landing and the floor slab), the collision detection misses it. The ground truth says these stairs are "not connected to slabs at the end" — the tool correctly identifies the concept but its geometry-based collision detection has a different sensitivity than Solibri's.

**Secondary: E8 — Model-specific IFC structure.** The tool creates a new `tree` per stair, which may not include all relevant geometry context.

---

### 5. 504_2_non_uniform_risers_treads — F1=0.000 (FP=1, FN=0)

**FP pattern:** 1 FP in 4351 (`2yrvjJLF5DO99bzmxJnJrl`).

**Root cause: E3 — Property lookup failure or E6 — Threshold mismatch.**
The tool flagged one element that the ground truth considers compliant. Since there are 0 expected violations on test models, this is a pure false alarm — likely a borderline riser height difference that falls within Solibri's tolerance but outside the tool's.

---

### 6. doors_and_windows — F1=0.250 (FP=12, FN=0)

**FP pattern:** 4 FPs in 4351, 8 FPs in samuel_macalister.

**Root cause: E7 — Missing rule logic / E4 — Relationship traversal gap.**
The tool checks floor-level mismatch between doors/windows and their host walls via `IfcRelFillsElement → IfcRelVoidsElement`. The 12 FPs are doors/windows where the tool detects a floor mismatch but Solibri doesn't consider them violations. Possible reasons:
- The tool flags doors whose `get_container()` returns a different storey than the wall's container, but in some models storeys overlap or doors span storey boundaries legitimately.
- The tool also flags elements where `elem_floor_id is None` — doors without a spatial container get flagged even if they're valid.

---

### 7. clearance_front_of_doors — F1=0.154 (FP=61, FN=5)

**FP pattern (61 total):** 1 in 4351, 58 in digital_hub, 2 in wbdg_office.

**FN pattern (5 total):** 2 in 4351, 2 in samuel_macalister, 1 in wbdg_office.

**Root cause (FP): E5 — Geometry approximation error.**
The tool creates a clearance box from the door's local placement (`ObjectPlacement`), but:
1. The clearance zone is only projected **one side** (positive Y direction). The rule says "check both sides: false", but the local Y direction may not correspond to the actual swing side of the door.
2. The tool uses **bounding box intersection** for collision detection, which is very coarse — any element whose AABB overlaps the clearance box counts, even if the actual geometry doesn't intersect.
3. The clearance zone's Z-range is hard-coded from 0 to 2.1m (`clearance_min[2] = 0`), which ignores the door's actual elevation.

The 58 FPs in digital_hub strongly suggest the bounding box check is too permissive — almost every building element overlaps some door's clearance box.

**Root cause (FN): E5 + E7.**
The 5 FNs involve components (slabs, walls, sanitary terminals) intersecting clearance areas. The tool may miss these because:
- It only checks `IfcBuildingElement`, which may not include `IfcSanitaryTerminal` (the wbdg_office FN).
- The one-directional clearance zone may face the wrong direction.

---

### 8. large_spaces_more_than_one_door — F1=0.267 (FP=1, FN=21)

**FN pattern (21 total):** 3 in 4351, 11 in digital_hub, 2 in samuel_macalister, 5 in wbdg_office. All say "Count (0) of components does not match the requirement >= 2".

**Root cause: E4 — Relationship traversal gap.**
The tool counts doors per space using `IfcRelSpaceBoundary`. In many models, `IfcRelSpaceBoundary` is **incomplete or absent** — spaces have doors geometrically adjacent to them, but no explicit boundary relationship. The ground truth (Solibri) uses geometric containment to count doors, while the tool relies purely on explicit IFC relationships.

The FN descriptions all say "Count (0) of the components" — meaning the tool found 0 doors for these spaces, confirming the relationship data is missing.

**Secondary: E8 — Model-specific IFC structure.** The digital_hub model (11 FN) likely has poor or missing IfcRelSpaceBoundary data.

---

### 9. slabs_guarded_against_falling — F1=0.052 (FP=15, FN=58)

**This is the worst-performing rule.**

**FN pattern (58 total):** Massive misses across all models. Ground truth identifies slabs with barriers that are too low (e.g. 0.91m vs required 1.0m), slabs missing barriers entirely, and slabs with excessive drops to adjacent surfaces.

**Root causes:**

**E5 — Geometry approximation error (primary).** The tool:
1. Uses **convex hull** for barrier footprints, which over-estimates coverage and marks edges as "protected" when they aren't.
2. Samples perimeter points every 0.05m and uses a 0.15m gap tolerance — barriers with small gaps or offset placement get incorrectly counted as protection.
3. Only considers barriers whose `bottom_z <= ref_z + 0.2` — barriers on elevated bases may be missed.

**E7 — Missing rule logic.**
- The ground truth distinguishes between "barrier too low" and "barrier missing" — the tool doesn't differentiate these failure modes.
- The tool doesn't check for "adjacent landing components too far below" (the max_fall=0.5m case) robustly enough.
- Barrier height is computed as `top_z - bottom_z` of the entire element, not relative to the slab top — a wall that starts below the slab would have inflated height.

**FP pattern (15 total):** The tool flags slabs that Solibri considers adequately protected. This may be due to the convex hull being too coarse in some cases, or the 0.1m max unprotected segment threshold being stricter than Solibri's.

---

### 10. space_validation_inside — F1=0.300 (FP=0, FN=14)

**FN pattern (14 total):** 9 in digital_hub, 1 in samuel_macalister, 4 in wbdg_office.

**Root cause: E5 — Geometry approximation error.**
The tool checks if **ALL** vertices of a component are inside the space mesh (`np.all(contains)`). This is extremely strict — if even one vertex protrudes, the component isn't flagged. The ground truth likely uses a more lenient criterion (e.g. centroid inside, or majority of volume inside).

The ground truth descriptions mention components like "Slab.-1.1.1 are inside the space" and "Wall.-1.19 are inside the space" — these are partial containments where most of the element is inside but not every single vertex.

**Secondary: E7.** The ground truth also flags spaces where "Space doesn't touch slab, roof, or space surface below itself at all" — this is a separate sub-rule that the tool doesn't implement.

---

### 11. space_validation_intersect — F1=0.444 (FP=48, FN=2)

**FP pattern (48 total):** 1 in 4351, 44 in digital_hub, 1 in samuel_macalister, 2 in wbdg_office.

**Root cause: E6 — Threshold mismatch / E5 — Geometry precision.**
The tool uses `tree.clash_intersection_many()` with `tolerance=0.03` and then excludes elements fully inside the space. The 44 FPs in digital_hub suggest the tool is detecting intersections that Solibri considers acceptable (within tolerance). The `completely_within` exclusion may not work correctly for all element types.

**FN pattern (2 total):** 2 missed in 4351 — spaces that intersect with walls but weren't detected, possibly because the geometry tree didn't include all relevant elements.

---

### 12. 305_3_size — F1=0.000 (FP=7, FN=1)

**FP pattern (7 total):** 5 in samuel_macalister, 2 in wbdg_office.

**Root cause: E5 — Geometry approximation error + E7 — Missing rule logic.**
The tool uses random sampling (20 random points) to check if a 760x1220mm rectangle fits in a space. This Monte Carlo approach:
1. Is non-deterministic — different runs may give different results.
2. May fail to find valid placements in spaces with complex geometry.
3. Returns **furniture GUIDs** as representatives, not space GUIDs — this is an E1 (GUID strategy mismatch).

**FN (1 total):** The tool missed `0lntrd6l1AGwfcnKJK5r3q` (Master Bedroom in samuel_macalister) — the space has inaccessible areas that the random sampling failed to detect as violations.

---

### 13. 404_2_5_two_doors_in_series — F1=0.000 (FP=46, FN=1)

**FP pattern (46 total):** All 46 in wbdg_office.

**Root cause: E4 — Relationship traversal gap + E7 — Missing rule logic.**
The tool finds all door pairs in circulation spaces (via IfcRelSpaceBoundary) that are closer than 1.22m. The 46 FPs in wbdg_office suggest:
1. The tool pairs ALL doors in the same circulation space, not just doors "in series" (sequentially along a corridor).
2. Solibri's rule specifically checks for doors in series (vestibule-style arrangements), not just any two nearby doors.
3. The tool doesn't account for door swing width being added to the minimum distance.

**FN (1 total):** Missed door pair in samuel_macalister (`3ch3OBgkrCEw4mDhJ2eOWH`) — 1.16m distance. The tool may have missed this because the model lacks IfcRelSpaceBoundary for that space, so the doors weren't paired.

---

### 14. unallocated_areas — F1=0.000 (FP=13, FN=20)

**FP pattern (13 total):** 5 in 4351, 5 in digital_hub, 3 in wbdg_office.

**FN pattern (20 total):** 8 in digital_hub, 12 in samuel_macalister.

**Root cause: E5 — Geometry approximation error + E1 — GUID strategy mismatch.**
The tool:
1. Constructs wall buffers from centerlines (0.2m buffer), then subtracts space footprints and slab footprints.
2. Returns **surrounding wall GUIDs**, which must match the ground truth's expected wall GUIDs exactly.

The approach is fundamentally fragile because:
- Wall centerline extraction (`get_wall_centerline`) uses the longest edge of the footprint polygon — this is a poor approximation for non-rectangular walls.
- The 0.2m buffer doesn't match actual wall thickness, leading to incorrect unallocated area computation.
- The ground truth expects a specific set of surrounding wall GUIDs per unallocated area, and even small geometry differences change which walls are "surrounding."

---

## Summary of Error Sources

| Error Source | Rules Affected | Impact |
|---|---|---|
| **E5: Geometry approximation** | slabs_guarded, clearance_doors, space_inside, space_intersect, 305_3, unallocated, stair_slab | Largest source of errors — convex hulls, bounding boxes, and sampling-based approaches are too coarse |
| **E4: Relationship traversal** | large_spaces, 404_2_5, doors_windows | IFC relationship data (IfcRelSpaceBoundary) is incomplete in many models |
| **E2: Over-inclusive traversal** | riser_height | Returning sub-element GUIDs that ground truth doesn't expect |
| **E7: Missing rule logic** | slabs_guarded, clearance_doors, 305_3, 404_2_5 | Tool doesn't implement the full complexity of the rule |
| **E3: Property lookup failure** | slab_thickness, non_uniform | Properties stored in unexpected psets or missing entirely |
| **E1: GUID strategy mismatch** | riser_height, tread_length, 305_3, unallocated | Wrong element type returned |
| **E6: Threshold mismatch** | space_intersect, non_uniform | Different tolerance/threshold than Solibri |
| **E8: Model-specific structure** | large_spaces, stair_slab | Model-specific IFC structuring breaks assumptions |
