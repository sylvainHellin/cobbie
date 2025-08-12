import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Set

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
    
    # Get all spaces
    spaces = model.by_type("IfcSpace")
    
    # Create a mapping from space GlobalId to space name for easy lookup
    space_id_to_name = {space.GlobalId: space.Name for space in spaces}
    
    # Create a mapping from space to its connected building elements
    space_to_elements = {}
    
    # Get all IfcRelSpaceBoundary entities
    rel_space_boundaries = model.by_type("IfcRelSpaceBoundary")
    
    # For each boundary, map the space to its connected building element
    for boundary in rel_space_boundaries:
        if hasattr(boundary, 'RelatingSpace') and boundary.RelatingSpace:
            space = boundary.RelatingSpace
            space_id = space.GlobalId
            
            # Initialize the set for this space if not already done
            if space_id not in space_to_elements:
                space_to_elements[space_id] = set()
            
            # Add the related building element if it exists
            if (hasattr(boundary, 'RelatedBuildingElement') and 
                boundary.RelatedBuildingElement):
                element = boundary.RelatedBuildingElement
                space_to_elements[space_id].add(element.GlobalId)
    
    # Now find adjacent spaces based on shared building elements
    adjacent_spaces = {}
    
    # Initialize the adjacency dictionary with all spaces
    for space in spaces:
        adjacent_spaces[space.Name] = []
    
    # Compare each pair of spaces to see if they share building elements
    space_ids = list(space_to_elements.keys())
    for i in range(len(space_ids)):
        space_id_1 = space_ids[i]
        space_name_1 = space_id_to_name[space_id_1]
        elements_1 = space_to_elements[space_id_1]
        
        for j in range(i + 1, len(space_ids)):
            space_id_2 = space_ids[j]
            space_name_2 = space_id_to_name[space_id_2]
            elements_2 = space_to_elements[space_id_2]
            
            # Check if they share any building elements
            if elements_1.intersection(elements_2):
                # They are adjacent
                adjacent_spaces[space_name_1].append(space_name_2)
                adjacent_spaces[space_name_2].append(space_name_1)
    
    return adjacent_spaces