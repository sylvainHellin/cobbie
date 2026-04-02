import ifcopenshell
import ifcopenshell.util.element
from typing import List

def check_doors_and_windows(path_ifc_model: str) -> List[str]:
    """
    Check doors and windows for BIM validation rule compliance.
    
    This function verifies that:
    1. Doors and windows are related to a wall or other building element (not orphaned)
    2. Doors and windows are located in the same floor as the building element they are related to
    
    Args:
        path_ifc_model: Path to the IFC model file
        
    Returns:
        List of IFC GUIDs of elements that violate the rules:
        - Orphan doors/windows (no valid relation to any building element)
        - Doors/windows on different floor than their related building element
        
    Example:
        >>> violations = check_doors_and_windows('model.ifc')
        >>> print(violations)
        ['1oCmeD_UH0NAQ13DTKAKXn', '2NHD_$8fb3ZexljM$wSStT']
    """
    model = ifcopenshell.open(path_ifc_model)
    violations = []
    
    # Check both doors and windows
    for ifc_class in ['IfcDoor', 'IfcWindow']:
        for element in model.by_type(ifc_class):
            guid = element.GlobalId
            
            # Get the element's container (building storey)
            element_container = ifcopenshell.util.element.get_container(element)
            
            # Check FillsVoids relationship
            fills_voids = element.FillsVoids
            
            if not fills_voids:
                # No opening relationship - could be orphan, but check if it decomposes other elements
                # If element has children (Decomposes), it's a parent in a system, not an orphan
                has_children = False
                if hasattr(element, 'Decomposes') and element.Decomposes:
                    has_children = True
                
                if not has_children:
                    # No wall relationship AND no children - ORPHAN
                    violations.append(guid)
                continue
            
            # Check all openings to find a valid building element relationship
            found_building_element = False
            floor_mismatch = False
            
            for rel in fills_voids:
                opening = rel.RelatingOpeningElement
                if not opening:
                    continue
                
                # Get opening's container
                opening_container = ifcopenshell.util.element.get_container(opening)
                
                # Check VoidsElements relationship (Opening -> Building Element)
                voids_elements = opening.VoidsElements
                
                if not voids_elements:
                    # Opening has no voids - check next opening
                    continue
                
                for void_rel in voids_elements:
                    building_elem = void_rel.RelatingBuildingElement
                    if not building_elem:
                        continue
                    
                    # Found a valid building element
                    found_building_element = True
                    
                    # Check floor mismatch: compare element container with opening container
                    if element_container and opening_container:
                        if element_container.GlobalId != opening_container.GlobalId:
                            floor_mismatch = True
                            violations.append(guid)
                            break  # Already have a floor mismatch, no need to check further
                
                if floor_mismatch or found_building_element:
                    break  # No need to check other openings
            
            # Only add as orphan if we checked all openings and found no valid building element
            if not found_building_element and not floor_mismatch:
                # Check if element decomposes other elements (has children)
                has_children = False
                if hasattr(element, 'Decomposes') and element.Decomposes:
                    has_children = True
                
                if not has_children:
                    violations.append(guid)
    
    return violations