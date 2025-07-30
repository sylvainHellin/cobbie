
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

def check_element_characteristics(ifc_file_path: str, element_type: str, property_names: List[str], expected_values: Optional[List[Any]] = None, filter_criteria: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Check if elements of a specified type have specific properties with certain values.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        element_type (str): IFC element type to check (e.g., 'IfcWall', 'IfcDoor', 'IfcSlab')
        property_names (List[str]): List of property names to check
        expected_values (Optional[List[Any]]): List of expected values for the properties.
            If provided, only elements matching these values will be returned.
            If None, all elements with the properties will be returned.
        filter_criteria (Optional[Dict[str, Any]]): Additional criteria to filter elements 
            by their property values before checking characteristics
        
    Returns:
        List[Dict[str, Any]]: List of dictionaries, each containing:
            - element_name: The element's name
            - element_guid: The element's GlobalId
            - element_type: The IFC type of the element
            - properties_found: Dictionary mapping property names to their actual values
            - matches_expected: Boolean indicating if the element's properties match the expected values (only included if expected_values is provided)
            - spatial_info: Dictionary with spatial relationship information (storey, space if available)
    """
    # Open the IFC file
    model = ifcopenshell.open(ifc_file_path)
    
    # Retrieve all elements of the specified type
    elements = model.by_type(element_type)
    
    results = []
    
    # Process each element
    for element in elements:
        # Get all property sets for the element
        psets = ifcopenshell.util.element.get_psets(element)
        
        # Extract element information
        element_info = {
            "element_name": element.Name if hasattr(element, 'Name') else None,
            "element_guid": element.GlobalId if hasattr(element, 'GlobalId') else None,
            "element_type": element.is_a(),
            "properties_found": {},
            "spatial_info": {}
        }
        
        # Search for specified properties across all property sets
        for prop_name in property_names:
            found_value = None
            # Look through all property sets for the property
            for pset_name, pset_dict in psets.items():
                if prop_name in pset_dict:
                    found_value = pset_dict[prop_name]
                    break
            
            element_info["properties_found"][prop_name] = found_value
        
        # Extract spatial information
        container = ifcopenshell.util.element.get_container(element)
        if container:
            element_info["spatial_info"]["storey"] = container.Name if hasattr(container, 'Name') else None
        
        # Apply filter criteria if provided
        if filter_criteria:
            should_include = True
            for filter_prop, filter_value in filter_criteria.items():
                # Look for filter property in the element's properties
                filter_prop_value = None
                for pset_name, pset_dict in psets.items():
                    if filter_prop in pset_dict:
                        filter_prop_value = pset_dict[filter_prop]
                        break
                
                # If filter property not found or doesn't match criteria, exclude element
                if filter_prop_value != filter_value:
                    should_include = False
                    break
            
            if not should_include:
                continue  # Skip this element
        
        # Check if properties match expected values if provided
        if expected_values is not None:
            matches = True
            for i, prop_name in enumerate(property_names):
                if i < len(expected_values):
                    actual_value = element_info["properties_found"][prop_name]
                    if actual_value != expected_values[i]:
                        matches = False
                        break
            
            element_info["matches_expected"] = matches
            
            # Only include in results if matches expected values
            if matches:
                results.append(element_info)
        else:
            # If no expected values, include all elements
            results.append(element_info)
    
    return results
