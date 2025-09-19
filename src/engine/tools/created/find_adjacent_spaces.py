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
    
    # Get all IfcRelSpaceBoundary entities
    rel_space_boundaries = model.by_type("IfcRelSpaceBoundary")
    
    # Create a mapping of building elements to their connected spaces
    element_to_spaces = {}
    
    # Process each boundary to map elements to spaces
    for boundary in rel_space_boundaries:
        if (hasattr(boundary, 'RelatingSpace') and boundary.RelatingSpace and 
            hasattr(boundary, 'RelatedBuildingElement') and boundary.RelatedBuildingElement):
            
            space = boundary.RelatingSpace
            element = boundary.RelatedBuildingElement
            
            # Only consider internal boundaries for adjacency
            internal_or_external = getattr(boundary, 'InternalOrExternalBoundary', None)
            if internal_or_external and internal_or_external.upper() != 'INTERNAL':
                continue
                
            element_id = element.GlobalId
            space_name = space.Name if space.Name else space.GlobalId
            
            if element_id not in element_to_spaces:
                element_to_spaces[element_id] = []
            
            # Store the space information
            element_to_spaces[element_id].append(space_name)
    
    # Now find which elements connect exactly two spaces (potential adjacency)
    adjacency_candidates = {}
    for element_id, spaces_list in element_to_spaces.items():
        # Remove duplicates while preserving order
        unique_spaces = []
        for space in spaces_list:
            if space not in unique_spaces:
                unique_spaces.append(space)
        
        # Only consider elements that connect exactly two spaces
        if len(unique_spaces) == 2:
            # Create a key for the pair (order doesn't matter)
            pair_key = tuple(sorted([unique_spaces[0], unique_spaces[1]]))
            
            if pair_key not in adjacency_candidates:
                adjacency_candidates[pair_key] = []
            adjacency_candidates[pair_key].append(element_id)
    
    # Build the adjacency dictionary
    adjacent_spaces = {}
    
    # Get all spaces to initialize the dictionary
    spaces = model.by_type("IfcSpace")
    for space in spaces:
        space_name = space.Name if space.Name else space.GlobalId
        adjacent_spaces[space_name] = []
    
    # Add the adjacent spaces
    for (space1, space2), elements in adjacency_candidates.items():
        if space1 not in adjacent_spaces:
            adjacent_spaces[space1] = []
        if space2 not in adjacent_spaces:
            adjacent_spaces[space2] = []
            
        if space2 not in adjacent_spaces[space1]:
            adjacent_spaces[space1].append(space2)
        if space1 not in adjacent_spaces[space2]:
            adjacent_spaces[space2].append(space1)
    
    return adjacent_spaces