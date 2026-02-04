import ifcopenshell
import ifcopenshell.util.element
from typing import List


def check_doors_and_windows(path_ifc_model: str) -> List[str]:
    """
    Validates doors and windows in an IFC model to ensure:
    1. Doors/windows are located in the same floor (IfcBuildingStorey) as the wall they are related to
    2. No orphan doors/windows exist (a door or window without a relation to any wall)

    The function checks for wall relationships using IfcRelVoidsElement connections,
    which is the standard IFC method for relating doors/windows to walls through openings.

    Args:
        path_ifc_model: Path to the IFC model file

    Returns:
        List of IFC GUIDs of all doors/windows that violate the rule.
        Violations include:
        - Orphan doors/windows (no related wall found)
        - Doors/windows on a different floor than their related wall

    Example:
        >>> violations = check_doors_and_windows('/path/to/model.ifc')
        >>> print(f"Found {len(violations)} violations")
    """
    model = ifcopenshell.open(path_ifc_model)
    
    # Build a lookup map from door/window GUID to their related wall
    # Using IfcRelVoidsElement → IfcOpeningElement → IfcRelFillsElement chain
    wall_lookup = {}  # Maps door/window GUID -> wall element
    skipped_rels = 0
    
    for rel in model.by_type('IfcRelVoidsElement'):
        try:
            wall = rel.RelatingBuildingElement
            opening = rel.RelatedOpeningElement
            
            # Check if this opening has any fillings (doors/windows)
            if hasattr(opening, 'HasFillings'):
                for filling in opening.HasFillings:
                    if hasattr(filling, 'RelatedBuildingElement'):
                        filled_elem = filling.RelatedBuildingElement
                        if filled_elem.is_a() in ('IfcDoor', 'IfcWindow'):
                            wall_lookup[filled_elem.GlobalId] = wall
        except AttributeError:
            skipped_rels += 1
            continue
    
    if skipped_rels > 0:
        print(f"Warning: Skipped {skipped_rels} IfcRelVoidsElement relations due to missing attributes")
    
    # Check all doors and windows for violations
    violations = []
    orphan_count = 0
    storey_mismatch_count = 0
    skipped_elements = 0
    
    for elem in model.by_type('IfcDoor') + model.by_type('IfcWindow'):
        try:
            guid = elem.GlobalId
            
            # Check if orphan (no related wall found through standard relationship)
            if guid not in wall_lookup:
                orphan_count += 1
                violations.append(guid)
                continue
            
            # Get storey of door/window
            door_container = ifcopenshell.util.element.get_container(elem)
            door_storey_id = None
            if door_container and door_container.is_a() == 'IfcBuildingStorey':
                door_storey_id = door_container.GlobalId
            
            # Get storey of related wall
            wall = wall_lookup[guid]
            wall_container = ifcopenshell.util.element.get_container(wall)
            wall_storey_id = None
            if wall_container and wall_container.is_a() == 'IfcBuildingStorey':
                wall_storey_id = wall_container.GlobalId
            
            # Compare storeys - only flag as violation if both have storeys and they differ
            # If either has no storey, we can't definitively determine a mismatch
            if door_storey_id and wall_storey_id and door_storey_id != wall_storey_id:
                storey_mismatch_count += 1
                violations.append(guid)
                
        except AttributeError:
            skipped_elements += 1
            continue
    
    if skipped_elements > 0:
        print(f"Warning: Skipped {skipped_elements} door/window elements due to missing attributes")
    
    return violations