
import ifcopenshell
from typing import List, Dict, Any

def get_property_values_from_elements_by_type(
    file_path: str,
    element_type: str,
    property_names: List[str],
    pset_names: List[str]
) -> Dict[str, Any]:
    """
    Extract property values from IFC elements of a specific type.
    
    Args:
        file_path (str): Path to the IFC file
        element_type (str): Type of IFC elements to query (e.g., 'IfcWall', 'IfcSlab')
        property_names (List[str]): List of property names to extract
        pset_names (List[str]): List of property set names to search in
        
    Returns:
        Dict[str, Any]: Dictionary mapping property names to their values
    """
    # Open the IFC file
    model = ifcopenshell.open(file_path)
    
    # Get all elements of the specified type
    elements = model.by_type(element_type)
    
    # Initialize result dictionary
    result = {}
    
    # For each property name, try to find its value
    for prop_name in property_names:
        # Check each element
        for element in elements:
            # Check each property set name
            for pset_name in pset_names:
                # Try to get the property set
                psets = ifcopenshell.util.element.get_psets(element)
                if pset_name in psets and prop_name in psets[pset_name]:
                    result[prop_name] = psets[pset_name][prop_name]
                    break
            # If we found the property, no need to check other elements
            if prop_name in result:
                break
    
    return result
