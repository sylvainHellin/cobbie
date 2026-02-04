import ifcopenshell
import ifcopenshell.util.element
from typing import List

def check_large_spaces_more_than_one_door(path_ifc_model: str) -> List[str]:
    """
    Check if large spaces (area ≥ 50.0) have at least 2 doors.
    
    Large spaces must have at least 2 doors, excluding:
    - Spaces with usage: Outdoor Space, Parking, Terrace
    - Spaces with 'roof' in the name (typically outdoor/excluded)
    - Doors that are hatches
    
    Args:
        path_ifc_model: Path to the IFC model file
        
    Returns:
        List of IFC GUIDs of spaces that violate the rule (large spaces
        with fewer than 2 doors)
        
    Example:
        >>> violations = check_large_spaces_more_than_one_door('model.ifc')
        >>> print(f"Found {len(violations)} violations")
    """
    model = ifcopenshell.open(path_ifc_model)
    violations = []
    
    # Get all spaces
    spaces = model.by_type("IfcSpace")
    if not spaces:
        return violations
    
    # Prepare space data for classification
    spaces_data = []
    for space in spaces:
        spaces_data.append({
            "guid": space.GlobalId,
            "name": space.LongName or space.Name or ""
        })
    
    # Classify spaces
    classified_spaces = classify_spaces(spaces_data, path_ifc_model)
    
    # Create classification lookup
    classification_map = {s["guid"]: s["classification"] for s in classified_spaces}
    
    # Excluded space usages
    excluded_usages = {"Outdoor Space", "Parking", "Terrace"}
    
    skipped = 0
    
    for space in spaces:
        try:
            guid = space.GlobalId
            name_lower = (space.LongName or space.Name or "").lower()
            
            # Skip excluded space usages
            classification = classification_map.get(guid, "Unclassified")
            if classification in excluded_usages:
                continue
            
            # Skip roof spaces (typically outdoor)
            if "roof" in name_lower:
                continue
            
            # Get space area
            area = None
            qtos = ifcopenshell.util.element.get_psets(space, qtos_only=True)
            
            # Try different quantity sets for area
            for qset_name, qset in qtos.items():
                # Check common area keys
                for area_key in ["GSA BIM Area", "Area", "NetFloorArea", "FloorArea"]:
                    if area_key in qset:
                        area = qset[area_key]
                        break
                if area is not None:
                    break
            
            if area is None:
                skipped += 1
                continue
            
            # Check if space is large enough (≥ 50.0)
            if area < 50.0:
                continue
            
            # Count doors (excluding hatches)
            door_count = 0
            for rel in space.BoundedBy:
                if rel.RelatedBuildingElement:
                    elem = rel.RelatedBuildingElement
                    if elem.is_a() == "IfcDoor":
                        # Check if it's a hatch
                        is_hatch = False
                        try:
                            door_type = ifcopenshell.util.element.get_type(elem)
                            if door_type and door_type.Name and "hatch" in door_type.Name.lower():
                                is_hatch = True
                        except (AttributeError, RuntimeError):
                            pass
                        
                        if not is_hatch:
                            door_count += 1
            
            # Check if space has at least 2 doors
            if door_count < 2:
                violations.append(guid)
                
        except (AttributeError, KeyError, RuntimeError) as e:
            skipped += 1
            continue
    
    if skipped > 0:
        print(f"Warning: Skipped {skipped} elements due to missing data or errors")
    
    return violations