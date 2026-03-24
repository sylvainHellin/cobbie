import ifcopenshell
import ifcopenshell.util.element
from typing import List
import os


def check_large_spaces_more_than_one_door(path_ifc_model: str) -> List[str]:
    """
    Check if large spaces (area >= 50) have at least 2 doors.
    
    Rule Parameters:
    - Include Space Group Type: Is Undefined (no filtering)
    - Include Space Area: >= 50.0
    - Exclude - Space Usage: One Of [Outdoor Space, Parking, Terrace]
    - Target Value: 2 doors minimum
    - Exclude door = Hatch
    
    Args:
        path_ifc_model: Path to the IFC model file
        
    Returns:
        List of IFC GUIDs of spaces that violate the rule
        (large spaces with fewer than 2 non-hatch doors)
        
    Example:
        >>> guids = check_large_spaces_more_than_one_door('model.ifc')
        >>> print(f"Found {len(guids)} violations")
    """
    model = ifcopenshell.open(path_ifc_model)
    violating_guids: List[str] = []
    
    # Get all spaces
    spaces = model.by_type('IfcSpace')
    if not spaces:
        return []
    
    # Get all IfcRelSpaceBoundary for door counting
    rel_boundaries = model.by_type('IfcRelSpaceBoundary')
    
    # Prepare space data for classification
    spaces_data = []
    for space in spaces:
        name = getattr(space, 'LongName', None) or getattr(space, 'Name', '') or ''
        spaces_data.append({"guid": space.GlobalId, "name": name})
    
    # Classify spaces
    classified = classify_spaces(spaces_data, path_ifc_model)
    
    # Create mapping from guid to classification
    classification_map = {c['guid']: c['classification'] for c in classified}
    
    # Excluded space usages
    excluded_usages = {'Outdoor Space', 'Parking', 'Terrace'}
    
    # Check each space
    for space in spaces:
        guid = space.GlobalId
        
        # Check if space is in excluded usage
        if guid not in classification_map:
            continue
        classification = classification_map[guid]
        if classification in excluded_usages:
            continue
        
        # Get space area
        psets = ifcopenshell.util.element.get_psets(space)
        area = None
        for pset_name, props in psets.items():
            if 'Area' in props:
                area_val = props['Area']
                if isinstance(area_val, (int, float)) and area_val >= 50.0:
                    area = area_val
                    break
        
        # Only check spaces with area >= 50
        if area is None:
            continue
        
        # Count doors (excluding hatch doors)
        door_count = 0
        for rel in rel_boundaries:
            if rel.RelatingSpace and rel.RelatingSpace.GlobalId == guid:
                if rel.RelatedBuildingElement and 'Door' in rel.RelatedBuildingElement.is_a():
                    door = rel.RelatedBuildingElement
                    
                    # Check if door is a hatch door (exclude)
                    is_hatch = False
                    door_name = getattr(door, 'Name', '')
                    if door_name and 'Hatch' in door_name:
                        is_hatch = True
                    
                    # Also check door properties for 'Hatch'
                    if not is_hatch:
                        door_psets = ifcopenshell.util.element.get_psets(door)
                        for pset_name, props in door_psets.items():
                            for key, val in props.items():
                                if isinstance(val, str) and 'Hatch' in val:
                                    is_hatch = True
                                    break
                            if is_hatch:
                                break
                    
                    if not is_hatch:
                        door_count += 1
        
        # Check if space has less than 2 doors
        if door_count < 2:
            violating_guids.append(guid)
    
    return violating_guids