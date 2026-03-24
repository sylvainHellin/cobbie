import ifcopenshell
import ifcopenshell.util.element
from typing import List

def check_doors_and_windows(path_ifc_model: str) -> List[str]:
    """
    Checks that doors and windows are located in the same floor as the wall they are related to.
    Also identifies orphan doors/windows (without a relation to any wall).

    Args:
        path_ifc_model: Path to the IFC model file.

    Returns:
        List of IFC GUIDs of all doors/windows that violate the rule:
        - Doors/windows not on the same floor as their related wall
        - Orphan doors/windows (no relation to any wall)

    Example:
        >>> violations = check_doors_and_windows("/path/to/model.ifc")
        >>> print(f"Found {len(violations)} violations")
    """
    model = ifcopenshell.open(path_ifc_model)
    violations = []

    # Process both doors and windows
    for element_class in ['IfcDoor', 'IfcWindow']:
        for elem in model.by_type(element_class):
            guid = elem.GlobalId
            
            # Get the container (floor/storey) of the door/window
            elem_container = ifcopenshell.util.element.get_container(elem)
            elem_floor_id = elem_container.id() if elem_container else None
            
            # Find the related wall through IfcRelFillsElement -> IfcRelVoidsElement chain
            related_wall = None
            
            # Find IfcRelFillsElement where this element is the RelatedBuildingElement
            for rel in model.by_type('IfcRelFillsElement'):
                if rel.RelatedBuildingElement.id() == elem.id():
                    opening = rel.RelatingOpeningElement
                    
                    # Find IfcRelVoidsElement for this opening
                    if hasattr(opening, 'VoidsElements'):
                        for void_rel in opening.VoidsElements:
                            if void_rel.is_a('IfcRelVoidsElement'):
                                related_wall = void_rel.RelatingBuildingElement
                                break
                    break
            
            # Only check violations if there's a related wall
            # (Don't flag standalone elements like curtain wall doors as orphans)
            if related_wall is not None:
                # Get the container (floor/storey) of the wall
                wall_container = ifcopenshell.util.element.get_container(related_wall)
                wall_floor_id = wall_container.id() if wall_container else None
                
                # Check if floors match
                if elem_floor_id is None or wall_floor_id is None:
                    # If either floor is None, it's a violation
                    violations.append(guid)
                elif elem_floor_id != wall_floor_id:
                    violations.append(guid)
    
    return violations