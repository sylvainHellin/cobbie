import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, Optional


def count_ifc_elements(
    model_path: str, 
    ifc_type: str, 
    name_pattern: str = None, 
    property_filter: dict = None
) -> int:
    """
    Count the number of instances of a specific IFC entity type in a BIM model.
    
    Args:
        model_path (str): Path to the IFC model file
        ifc_type (str): The IFC entity type to count (e.g., "IfcWindow", "IfcDoor", "IfcWall")
        name_pattern (str, optional): Pattern to filter elements by name (case-insensitive substring match)
        property_filter (dict, optional): Dictionary of property name-value pairs to filter elements.
            Properties can be:
            - Direct attributes of the element (e.g., 'Name', 'GlobalId', 'id')
            - Properties in the element's info dictionary
            - Properties within property sets (e.g., 'FireRating' in 'Pset_DoorCommon')
            Note: This function works with IFC models exported from Revit and similar BIM authoring software
            that include property sets like PSet_Revit_*.
        
    Returns:
        int: The count of elements matching the specified criteria
        
    Raises:
        Exception: If the model cannot be loaded or if the specified entity type doesn't exist
    """
    try:
        # Load the IFC model
        model = ifcopenshell.open(model_path)
    except Exception as e:
        raise Exception(f"Failed to load IFC model from {model_path}: {str(e)}")
    
    try:
        # Get all instances of the specified IFC type
        elements = model.by_type(ifc_type)
    except Exception as e:
        raise Exception(f"Failed to retrieve elements of type {ifc_type}: {str(e)}")
    
    # Apply name filtering if provided
    if name_pattern:
        name_pattern_lower = name_pattern.lower()
        filtered_elements = []
        for element in elements:
            # Check if element has a Name attribute
            if hasattr(element, 'Name') and element.Name:
                if name_pattern_lower in element.Name.lower():
                    filtered_elements.append(element)
        elements = filtered_elements
    
    # Apply property filtering if provided
    if property_filter:
        filtered_elements = []
        for element in elements:
            match = True
            
            # Get element info for checking properties
            element_info = element.get_info()
            
            for prop_name, prop_value in property_filter.items():
                property_found = False
                
                # Special handling for 'id' property (element ID)
                if prop_name == 'id':
                    if element.id() == prop_value:
                        property_found = True
                
                # Check if it's a direct attribute of the element
                elif hasattr(element, prop_name):
                    element_prop_value = getattr(element, prop_name)
                    # Handle comparison with None values and different types
                    if element_prop_value == prop_value:
                        property_found = True
                
                # Check if it's in the element's info dictionary
                elif prop_name in element_info:
                    if element_info[prop_name] == prop_value:
                        property_found = True
                
                # If not found directly, check in property sets
                else:
                    try:
                        # Get all property sets for the element
                        psets = ifcopenshell.util.element.get_psets(element)
                        for pset_name, pset_props in psets.items():
                            # Skip the 'id' key which is just the pset's own id
                            if pset_name == "id":
                                continue
                            # Check if the property exists in this property set and matches the value
                            # Look at actual property names and values, not the 'id' key
                            for pset_prop_name, pset_prop_value in pset_props.items():
                                if pset_prop_name == prop_name and pset_prop_value == prop_value:
                                    property_found = True
                                    break
                            if property_found:
                                break
                    except Exception:
                        # If we can't access property sets, continue checking other properties
                        pass
                
                # If this property wasn't found or didn't match, this element doesn't match
                if not property_found:
                    match = False
                    break
            
            if match:
                filtered_elements.append(element)
        
        elements = filtered_elements
    
    return len(elements)