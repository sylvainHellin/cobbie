
import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.util.placement
import ifcopenshell.util.geolocation
import ifcopenshell.util.system
import ifcopenshell.geom
import math
import json
from typing import *

def get_element_property_by_guid(ifc_file_path: str, element_guid: str, property_name: str, property_set_names: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Retrieves a specific property value from an IFC element identified by its GlobalId.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        element_guid (str): GlobalId of the element to search for the property
        property_name (str): Name of the property to retrieve
        property_set_names (Optional[List[str]]): Optional list of property set names to search within
        
    Returns:
        Dict[str, Any]: Dictionary containing property information
    """
    # Initialize result dictionary
    result = {
        'value': None,
        'unit': None,
        'source': None,
        'property_set_name': None,
        'element_name': None,
        'element_type': None,
        'success': False,
        'message': 'Property not found'
    }
    
    try:
        # Open the IFC file
        ifc_file = ifcopenshell.open(ifc_file_path)
        
        # Find the element by its GlobalId
        element = ifc_file.by_guid(element_guid)
        if element is None:
            result['message'] = f'Element with GlobalId {element_guid} not found'
            return result
            
        # Get element name and type
        result['element_name'] = getattr(element, 'Name', 'Unnamed')
        result['element_type'] = element.is_a()
        
        # First check if the property exists as a direct attribute of the element
        if hasattr(element, property_name):
            result['value'] = getattr(element, property_name)
            result['source'] = 'direct_attribute'
            result['success'] = True
            result['message'] = f'Property {property_name} found as direct attribute'
            return result
            
        # If not found as direct attribute, search through property sets
        # Get all property sets for the element
        property_sets = ifcopenshell.util.element.get_psets(element)
        
        # If property_set_names is provided, only search within those property sets
        if property_set_names is not None:
            # Filter property sets to only those specified
            filtered_psets = {name: pset for name, pset in property_sets.items() if name in property_set_names}
        else:
            # Search all property sets
            filtered_psets = property_sets
            
        # Search for the property in the property sets
        for pset_name, pset_properties in filtered_psets.items():
            # Skip the 'BaseQuantities' key if present
            if pset_name == 'BaseQuantities':
                continue
                
            if property_name in pset_properties:
                property_value = pset_properties[property_name]
                result['value'] = property_value
                result['source'] = 'property_set'
                result['property_set_name'] = pset_name
                result['success'] = True
                result['message'] = f'Property {property_name} found in property set {pset_name}'
                # Try to get unit information if available
                # Note: Unit extraction might require additional processing
                return result
                
        # If we get here, the property wasn't found
        result['message'] = f'Property {property_name} not found in element or specified property sets'
        return result
        
    except Exception as e:
        result['message'] = f'Error processing IFC file: {str(e)}'
        return result
