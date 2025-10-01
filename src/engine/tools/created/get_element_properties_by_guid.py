import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Any

def get_element_properties_by_guid(model_path: str, guid: str, property_names: List[str]) -> Dict[str, Any]:
    """
    Retrieves specific properties of an IFC element given its GlobalId.
    
    This function searches across all property sets including standard IFC property sets
    and Revit-specific ones (PSet_Revit_*). It works with common IFC element types such
    as IfcWall, IfcSlab, IfcDoor, IfcWindow, IfcSpace, etc.
    
    Args:
        model_path (str): Path to the IFC model file
        guid (str): GlobalId of the element to retrieve properties from
        property_names (List[str]): List of property names to retrieve
        
    Returns:
        Dict[str, Any]: Dictionary with property names as keys and their values.
                        If a property is not found or has no value, its value will be None.
                        
    Raises:
        FileNotFoundError: If the model file is not found
        Exception: If there are issues accessing the element or its properties
    """
    try:
        # Load the IFC model
        model = ifcopenshell.open(model_path)
        
        # Find the element by its GlobalId
        element = model.by_guid(guid)
        
        if element is None:
            raise ValueError(f"No element found with GlobalId: {guid}")
        
        # Get all property sets for the element
        psets = ifcopenshell.util.element.get_psets(element)
        
        # Initialize result dictionary with None values
        result = {prop_name: None for prop_name in property_names}
        
        # Search for each requested property across all property sets
        for prop_name in property_names:
            # Look through each property set for the property
            for pset_name, pset_properties in psets.items():
                # Check if the property exists in this property set and is not the 'id' key
                if prop_name in pset_properties and prop_name != 'id':
                    prop_value = pset_properties[prop_name]
                    # Check if the property has a meaningful value
                    # If the value is the same as the property name, it's likely a placeholder
                    # Also check for other common placeholder values
                    if (prop_value is not None and 
                        prop_value != "" and 
                        str(prop_value).strip() != prop_name and
                        not (isinstance(prop_value, str) and prop_value.strip().lower() in ['undefined', 'none', 'n/a'])):
                        result[prop_name] = prop_value
                        break  # Found a meaningful value, no need to check other sets
                    # If we found the property but it has no meaningful value, we continue to look in other sets
                    # Only if we haven't found a meaningful value yet
        
        return result
    
    except FileNotFoundError:
        raise FileNotFoundError(f"Model file not found: {model_path}")
    except ValueError as ve:
        # Re-raise ValueError for invalid GUID
        raise ve
    except Exception as e:
        # Handle other exceptions
        raise Exception(f"Error retrieving properties for element {guid}: {str(e)}")