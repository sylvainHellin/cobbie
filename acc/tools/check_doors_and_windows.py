import ifcopenshell
import ifcopenshell.util.element
from typing import List


def check_doors_and_windows(model: ifcopenshell.file) -> List[str]:
    """
    Checks that doors and windows in the model are located in the same floor 
    as the wall they are related to. Also checks for orphan doors or windows 
    (elements without a relation to any wall).

    Args:
        model (ifcopenshell.file): The IFC model to check.

    Returns:
        List[str]: A list of IFC GUIDs of doors and windows that violate the rule.

    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('model.ifc')
        >>> violations = check_doors_and_windows(model)
        >>> print(f"Found {len(violations)} violations.")
    """
    violating_guids: List[str] = []
    
    try:
        # Get all doors and windows
        elements = model.by_type('IfcDoor') + model.by_type('IfcWindow')
        
        for element in elements:
            element_guid = element.GlobalId
            
            # Get the spatial container (storey) for the element
            element_container = ifcopenshell.util.element.get_container(element)
            
            # Find the related wall
            # The chain is typically: Element -> IfcRelFillsElement -> IfcOpeningElement -> IfcRelVoidsElement -> Wall
            related_wall = None
            
            # Step 1: Find IfcRelFillsElement pointing to this element
            fills_rels = [rel for rel in model.get_inverse(element) if rel.is_a('IfcRelFillsElement')]
            
            if fills_rels:
                for rel in fills_rels:
                    opening = rel.RelatingOpeningElement
                    if opening:
                        # Step 2: Find IfcRelVoidsElement pointing to this opening
                        voids_rels = [rel for rel in model.get_inverse(opening) if rel.is_a('IfcRelVoidsElement')]
                        if voids_rels:
                            # Found the host wall
                            related_wall = voids_rels[0].RelatingBuildingElement
                            break
            
            if related_wall:
                # Check storey consistency
                wall_container = ifcopenshell.util.element.get_container(related_wall)
                
                # If containers are different, it's a violation
                if element_container != wall_container:
                    violating_guids.append(element_guid)
            else:
                # No wall relation found (Orphan)
                violating_guids.append(element_guid)
                
    except Exception as e:
        print(f"Error during validation: {e}")
        raise
        
    return violating_guids