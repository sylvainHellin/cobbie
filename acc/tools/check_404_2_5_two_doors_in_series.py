import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.geom
import numpy as np
from typing import List, Dict, Set, Tuple


def check_404_2_5_two_doors_in_series(path_ifc_model: str) -> List[str]:
    """
    Check compliance with Rule 404.2.5: Two Doors in Series.
    
    Distance between two hinged or pivoted doors in series shall be 48 inches (1220 mm) 
    minimum plus the width of any door swinging into the space.
    
    Args:
        path_ifc_model: Path to the IFC model file.
        
    Returns:
        List of IFC GUIDs of doors that violate this rule.
        
    Example:
        >>> violations = check_404_2_5_two_doors_in_series('model.ifc')
        >>> print(f'Found {len(violations)} violating doors')
    """
    model = ifcopenshell.open(path_ifc_model)
    
    # Get all doors
    doors = model.by_type('IfcDoor')
    if not doors:
        return []
    
    # Get all spaces for classification
    spaces = model.by_type('IfcSpace')
    spaces_data = [{'guid': s.GlobalId, 'name': s.LongName or s.Name or ''} for s in spaces]
    
    # Classify spaces to identify circulation spaces
    classified_spaces = classify_spaces(spaces_data, path_ifc_model)
    circulation_space_guids = {s['guid'] for s in classified_spaces if s.get('classification') == 'Circulation'}
    
    if not circulation_space_guids:
        return []
    
    # Get door-space relationships using IfcRelSpaceBoundary
    rel_boundaries = model.by_type('IfcRelSpaceBoundary')
    door_to_spaces: Dict[str, Set[str]] = {}  # door GUID -> set of space GUIDs
    space_to_doors: Dict[str, Set[str]] = {}  # space GUID -> set of door GUIDs
    
    for rel in rel_boundaries:
        if hasattr(rel, 'RelatedBuildingElement'):
            elem = rel.RelatedBuildingElement
            if elem and elem.is_a('IfcDoor'):
                door_guid = elem.GlobalId
                space = rel.RelatingSpace
                if space:
                    space_guid = space.GlobalId
                    if door_guid not in door_to_spaces:
                        door_to_spaces[door_guid] = set()
                    door_to_spaces[door_guid].add(space_guid)
                    
                    if space_guid not in space_to_doors:
                        space_to_doors[space_guid] = set()
                    space_to_doors[space_guid].add(door_guid)
    
    # Get door geometry centers for distance calculation
    door_centers: Dict[str, np.ndarray] = {}
    
    settings = ifcopenshell.geom.settings()
    settings.set(settings.DISABLE_OPENING_SUBTRACTIONS, True)
    
    skipped_doors = 0
    for door in doors:
        door_guid = door.GlobalId
        # Only process doors that have space connections
        if door_guid not in door_to_spaces:
            skipped_doors += 1
            continue
        try:
            # Get geometry center
            shape = ifcopenshell.geom.create_shape(settings, door)
            verts = np.array(shape.geometry.verts).reshape(-1, 3)
            center = verts.mean(axis=0)
            door_centers[door_guid] = center
        except Exception:
            skipped_doors += 1
            continue
    
    if len(door_centers) < 2:
        return []
    
    # Find door pairs in the same circulation space
    door_pairs: Set[Tuple[str, str]] = set()
    
    for space_guid in circulation_space_guids:
        if space_guid in space_to_doors:
            door_list = list(space_to_doors[space_guid])
            if len(door_list) >= 2:
                # Create all pairs of doors in this circulation space
                for i in range(len(door_list)):
                    for j in range(i + 1, len(door_list)):
                        door1 = door_list[i]
                        door2 = door_list[j]
                        
                        # Both doors must have geometry
                        if door1 in door_centers and door2 in door_centers:
                            pair = tuple(sorted([door1, door2]))
                            door_pairs.add(pair)
    
    if not door_pairs:
        return []
    
    # Check each door pair for distance violations
    violation_guids: Set[str] = set()
    min_distance = 1.22  # 1220 mm in meters
    
    for door1_guid, door2_guid in door_pairs:
        center1 = door_centers[door1_guid]
        center2 = door_centers[door2_guid]
        
        # Calculate horizontal distance (ignore Z difference)
        horizontal_dist = np.sqrt(
            (center1[0] - center2[0])**2 + 
            (center1[1] - center2[1])**2
        )
        
        # Check if distance is less than minimum
        if horizontal_dist < min_distance:
            violation_guids.add(door1_guid)
            violation_guids.add(door2_guid)
    
    return list(violation_guids)