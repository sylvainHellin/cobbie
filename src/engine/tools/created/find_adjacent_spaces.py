import ifcopenshell
from typing import Dict, List

def find_adjacent_spaces(ifc_file_path: str) -> Dict[str, List[str]]:
    """
    Find adjacent spaces in an IFC model based on shared building elements through IfcRelSpaceBoundary.
    
    This function determines actual room connectivity based on geometric adjacency or explicit IFC 
    relationships (IfcRelSpaceBoundary connections) rather than relying on naming conventions.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        
    Returns:
        Dict[str, List[str]]: A dictionary mapping each space name to a list of adjacent space names
        
    Example:
        {
            "1B07": ["1BC2"],
            "1BC2": ["1B07", "1B08"],
            ...
        }
    """
    # Load the IFC model
    model = ifcopenshell.open(ifc_file_path)
    
    # Initialize adjacency dictionary with all spaces
    adjacent_spaces: Dict[str, List[str]] = {}
    spaces = model.by_type("IfcSpace")
    for space in spaces:
        space_name = space.Name if space.Name else space.GlobalId
        adjacent_spaces[space_name] = []
    
    # Get all IfcRelSpaceBoundary entities
    rel_space_boundaries = model.by_type("IfcRelSpaceBoundary")
    
    # First approach: Check if RelatedSpace is populated (proper IFC approach)
    related_space_populated = any(
        hasattr(boundary, 'RelatedSpace') and boundary.RelatedSpace 
        for boundary in rel_space_boundaries
    )
    
    if related_space_populated:
        # Use RelatedSpace when available
        for boundary in rel_space_boundaries:
            if (hasattr(boundary, 'RelatingSpace') and boundary.RelatingSpace and
                hasattr(boundary, 'RelatedSpace') and boundary.RelatedSpace):
                
                # Only consider internal boundaries
                internal_or_external = getattr(boundary, 'InternalOrExternalBoundary', None)
                if internal_or_external and internal_or_external.upper() != 'INTERNAL':
                    continue
                
                space1 = boundary.RelatingSpace
                space2 = boundary.RelatedSpace
                
                space1_name = space1.Name if space1.Name else space1.GlobalId
                space2_name = space2.Name if space2.Name else space2.GlobalId
                
                # Add to adjacency list (avoid duplicates)
                if space2_name not in adjacent_spaces.get(space1_name, []):
                    adjacent_spaces[space1_name].append(space2_name)
                if space1_name not in adjacent_spaces.get(space2_name, []):
                    adjacent_spaces[space2_name].append(space1_name)
    else:
        # Fallback approach: Use building elements to determine adjacency
        # Group boundaries by their RelatedBuildingElement
        element_to_boundaries = {}
        for boundary in rel_space_boundaries:
            if (hasattr(boundary, 'RelatedBuildingElement') and boundary.RelatedBuildingElement and
                hasattr(boundary, 'RelatingSpace') and boundary.RelatingSpace):
                
                # Only consider internal boundaries
                internal_or_external = getattr(boundary, 'InternalOrExternalBoundary', None)
                if internal_or_external and internal_or_external.upper() != 'INTERNAL':
                    continue
                
                element = boundary.RelatedBuildingElement
                element_id = element.GlobalId
                
                if element_id not in element_to_boundaries:
                    element_to_boundaries[element_id] = []
                element_to_boundaries[element_id].append(boundary)
        
        # For elements that connect exactly two spaces, establish adjacency
        # But be more selective - only consider elements that typically connect spaces
        connecting_elements = {'IfcDoor', 'IfcWindow'}
        
        for element_id, boundaries in element_to_boundaries.items():
            # Get unique spaces connected to this element
            connected_spaces = []
            for boundary in boundaries:
                space = boundary.RelatingSpace
                space_name = space.Name if space.Name else space.GlobalId
                if space_name not in connected_spaces:
                    connected_spaces.append(space_name)
            
            # If exactly two spaces are connected by the same element, and it's a connecting element, they are adjacent
            if len(connected_spaces) == 2:
                # Check if this element is a connecting element (door, window, etc.)
                element_type = boundaries[0].RelatedBuildingElement.is_a()
                if element_type in connecting_elements or element_type.startswith('IfcDoor') or element_type.startswith('IfcWindow'):
                    space1_name, space2_name = connected_spaces
                    # Add to adjacency list (avoid duplicates)
                    if space2_name not in adjacent_spaces.get(space1_name, []):
                        adjacent_spaces[space1_name].append(space2_name)
                    if space1_name not in adjacent_spaces.get(space2_name, []):
                        adjacent_spaces[space2_name].append(space1_name)
    
    # Remove any empty adjacency lists for spaces with no neighbors
    for space_name in list(adjacent_spaces.keys()):
        if not adjacent_spaces[space_name]:
            del adjacent_spaces[space_name]
    
    return adjacent_spaces