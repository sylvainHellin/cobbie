import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.placement
import numpy as np
from typing import List, Optional, Set


def get_door_world_position(model: ifcopenshell.file, door: ifcopenshell.entity_instance) -> Optional[np.ndarray]:
    """Get the world position (X, Y, Z) of a door."""
    try:
        if not door.ObjectPlacement:
            return None
        matrix = ifcopenshell.util.placement.get_local_placement(door.ObjectPlacement)
        return matrix[:,3][:3]
    except (AttributeError, IndexError):
        return None


def get_connected_spaces(model: ifcopenshell.file, door: ifcopenshell.entity_instance) -> Set[ifcopenshell.entity_instance]:
    """Get all spaces connected to a door via IfcRelSpaceBoundary."""
    spaces = set()
    try:
        for rel in model.get_inverse(door):
            if rel.is_a('IfcRelSpaceBoundary') and rel.RelatingSpace:
                spaces.add(rel.RelatingSpace)
    except AttributeError:
        pass
    return spaces


def check_404_2_5_two_doors_in_series(path_ifc_model: str) -> List[str]:
    """
    Check if pairs of doors in series violate accessibility rule 404.2.5.
    
    Rule 404.2.5 Two Doors in Series:
    Distance between two hinged or pivoted doors in series shall be 48 inches (1220 mm) 
    minimum plus the width of any door swinging into the space.
    
    Parameters:
    - Space Classification: One space must be Circulation, the other can be any classification (*)
    - Door Defaults: Frame thickness = 0.03 m, Panel thickness = 0.04 m, Threshold height = 0.01 m
    
    Args:
        path_ifc_model: Path to the IFC model file
        
    Returns:
        List[str]: List of IFC GUIDs of doors that violate this rule
        
    Example:
        >>> guids = check_404_2_5_two_doors_in_series('/path/to/model.ifc')
        >>> print(f"Found {len(guids)} violations")
    """
    try:
        model = ifcopenshell.open(path_ifc_model)
    except Exception as e:
        print(f"Error opening IFC model: {e}")
        return []
    
    # Get all doors
    doors = model.by_type('IfcDoor')
    if not doors:
        return []
    
    # Get all spaces and classify them
    spaces = model.by_type('IfcSpace')
    space_classifications = {}
    
    if spaces:
        try:
            space_data = [{"guid": s.GlobalId, "name": getattr(s, 'LongName', None) or getattr(s, 'Name', '')} for s in spaces]
            classified = classify_spaces(space_data, path_ifc_model)
            space_classifications = {s['guid']: s['classification'] for s in classified}
        except Exception as e:
            print(f"Warning: Could not classify spaces: {e}")
    
    # Build door info structure
    door_info_list = []
    skipped_doors = 0
    
    for door in doors:
        try:
            position = get_door_world_position(model, door)
            if position is None:
                skipped_doors += 1
                continue
            
            connected_spaces = get_connected_spaces(model, door)
            
            # Check if any connected space is Circulation
            has_circulation = any(
                space_classifications.get(s.GlobalId) == 'Circulation' 
                for s in connected_spaces
            )
            
            door_info_list.append({
                'door': door,
                'guid': door.GlobalId,
                'position': position,
                'connected_spaces': connected_spaces,
                'has_circulation': has_circulation
            })
        except (AttributeError, KeyError):
            skipped_doors += 1
            continue
    
    if skipped_doors > 0:
        print(f"Warning: Skipped {skipped_doors} doors due to missing data")
    
    if len(door_info_list) < 2:
        return []
    
    # Find pairs of doors in series that violate the rule
    violation_guids = set()
    MIN_BASE_DISTANCE = 1.22  # 1220 mm in meters
    PROXIMITY_THRESHOLD = 2.1  # meters - doors within this range are considered potentially 'in series'
    VERTICAL_TOLERANCE = 0.3  # meters - doors must be on same floor
    
    for i, door1 in enumerate(door_info_list):
        for j, door2 in enumerate(door_info_list):
            if i >= j:
                continue
            
            # Check if they share at least one space (doors are in series)
            shared_spaces = door1['connected_spaces'] & door2['connected_spaces']
            
            # Check if at least one connects to a circulation space
            if not (door1['has_circulation'] or door2['has_circulation']):
                continue
            
            # Check if on same floor (within vertical tolerance)
            pos1 = door1['position']
            pos2 = door2['position']
            if abs(pos1[2] - pos2[2]) > VERTICAL_TOLERANCE:
                continue
            
            # Calculate horizontal distance
            horizontal_distance = np.sqrt(
                (pos1[0] - pos2[0])**2 + (pos1[1] - pos2[1])**2
            )
            
            # Doors must share a space OR be very close
            if not shared_spaces and horizontal_distance > 1.5:
                continue
            
            # Only consider doors within proximity threshold
            if horizontal_distance > PROXIMITY_THRESHOLD:
                continue
            
            # Check if distance is less than minimum required
            if horizontal_distance < MIN_BASE_DISTANCE:
                violation_guids.add(door1['guid'])
                violation_guids.add(door2['guid'])
    
    return sorted(list(violation_guids))