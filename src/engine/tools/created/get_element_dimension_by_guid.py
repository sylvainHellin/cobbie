
import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, Any

def get_element_dimension_by_guid(ifc_file_path: str, element_guid: str, dimension_name: str) -> Dict[str, Any]:
    """
    Retrieve a dimensional property of an IFC element by its GlobalId.
    
    This function searches for a specified dimension (e.g., Width, Height) in both
    direct attributes and property sets of an IFC element.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        element_guid (str): GlobalId of the element to search for
        dimension_name (str): Name of the dimension to retrieve (e.g., 'Width', 'Height')
        
    Returns:
        Dict[str, Any]: Dictionary containing:
            - 'value': The dimension value (float) or None if not found
            - 'unit': The unit of the dimension (str) or None if not available
            - 'source': Where the value was found ('direct_attribute', 'property_set', or None)
            - 'property_set_name': Name of the property set if found there, else None
    """
    # Open the IFC file
    model = ifcopenshell.open(ifc_file_path)
    
    # Find the element by GlobalId
    element = model.by_guid(element_guid)
    
    # First, check direct attributes
    # Common direct attribute names for dimensions
    direct_attr_mapping = {
        "Width": ["OverallWidth", "Width"],
        "Height": ["OverallHeight", "Height"],
    }
    
    # Check if dimension_name has known direct attribute mappings
    attr_names_to_check = direct_attr_mapping.get(dimension_name, [dimension_name])
    
    # Check direct attributes by iterating through all attributes
    for i in range(len(element)):
        attr_name = element.attribute_name(i)
        attr_value = element[i]
        
        # Check if this attribute matches what we're looking for
        if attr_name in attr_names_to_check and attr_value is not None:
            return {
                "value": float(attr_value),
                "unit": "m",  # IFC standard unit for length is meters
                "source": "direct_attribute",
                "property_set_name": None
            }
    
    # If not found in direct attributes, check property sets
    try:
        psets = ifcopenshell.util.element.get_psets(element)
        
        # Common property set names for dimensions
        dimensional_psets = [
            "PSet_Revit_Type_Dimensions", 
            "PSet_Revit_Dimensions", 
            "PSet_DoorCommon",
            "PSet_WindowCommon",
            "Pset_DoorCommon",
            "Pset_WindowCommon"
        ]
        
        # Check for any property set that contains the dimension
        for pset_name, pset_dict in psets.items():
            # Check if this is a dimensional property set
            is_dimensional_pset = (
                pset_name in dimensional_psets or 
                "dimension" in pset_name.lower()
            )
            
            if is_dimensional_pset:
                # Look for exact matches first
                for prop_name, prop_value in pset_dict.items():
                    if prop_name != "id" and dimension_name.lower() == prop_name.lower():
                        # Check if the value is numeric
                        if isinstance(prop_value, (int, float)) or (isinstance(prop_value, str) and prop_value.replace('.', '').replace('-', '').isdigit()):
                            return {
                                "value": float(prop_value),
                                "unit": "m",  # Assuming meters as standard IFC unit
                                "source": "property_set",
                                "property_set_name": pset_name
                            }
                
                # Look for partial matches (e.g., "Width" matching "NominalWidth")
                for prop_name, prop_value in pset_dict.items():
                    if prop_name != "id" and dimension_name.lower() in prop_name.lower():
                        # Check if the value is numeric
                        if isinstance(prop_value, (int, float)) or (isinstance(prop_value, str) and prop_value.replace('.', '').replace('-', '').isdigit()):
                            return {
                                "value": float(prop_value),
                                "unit": "m",  # Assuming meters as standard IFC unit
                                "source": "property_set",
                                "property_set_name": pset_name
                            }
    except Exception as e:
        pass  # If there's an error getting property sets, continue
    
    # If we reach here, the dimension was not found
    return {
        "value": None,
        "unit": None,
        "source": None,
        "property_set_name": None
    }
