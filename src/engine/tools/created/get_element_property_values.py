import ifcopenshell
import ifcopenshell.util.element
from typing import *

def get_element_property_values(
    element: ifcopenshell.entity_instance,
    property_names: List[str],
    property_set_names: List[str] = None
) -> Dict[str, Any]:
    """
    Retrieve specific property values from an IFC element.
    
    Args:
        element: The IFC element to extract properties from
        property_names: List of property names to look for (e.g., ['ExpectedLife', 'ThermalTransmittance'])
        property_set_names: Optional list of property set names to search within (e.g., ['Pset_MaterialCommon', 'Pset_WallCommon'])
        
    Returns:
        Dictionary mapping property names to their values. If a property is not found, 
        its value will be None.
        
    Note:
        This function works with IFC models from various BIM authoring software.
        For Revit-exported IFC models, property sets may have names like 'PSet_Revit_Type_Other'.
        Property set name matching is case-insensitive and handles variations in naming conventions.
        
        Some IFC models may contain placeholder values (where the property value equals the 
        property name) rather than actual data values.
    """
    # Get all property sets for the element
    all_psets = ifcopenshell.util.element.get_psets(element)
    
    # Filter property sets if specific names are provided
    if property_set_names:
        # Case-insensitive matching for property set names
        psets = {}
        normalized_filter_names = [n.replace('PSet_', 'Pset_').replace('PSET_', 'Pset_').lower() for n in property_set_names]
        
        for name, props in all_psets.items():
            # Normalize names for comparison (handle different naming conventions)
            normalized_name = name.replace('PSet_', 'Pset_').replace('PSET_', 'Pset_').lower()
            
            if normalized_name in normalized_filter_names:
                psets[name] = props
    else:
        psets = all_psets
    
    # Initialize result dictionary
    result = {}
    
    # Look for specified properties in the property sets
    for property_name in property_names:
        found = False
        for pset_name, properties in psets.items():
            # Check if the property exists in this property set
            # Exclude the 'id' field which is not a property we're interested in
            if property_name in properties and property_name != 'id':
                result[property_name] = properties[property_name]
                found = True
                break
        # If property not found, mark as None
        if not found:
            result[property_name] = None
    
    return result
