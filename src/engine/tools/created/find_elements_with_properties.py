import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.util.placement
import ifcopenshell.util.geolocation
import ifcopenshell.util.system
import ifcopenshell.geom
import math
import json
import re
from typing import *

def find_elements_with_properties(
    ifc_file_path: str,
    element_type: Optional[str] = None,
    property_names: Optional[List[str]] = None,
    pset_names: Optional[List[str]] = None,
    filter_criteria: Optional[Dict[str, Any]] = None,
    spatial_constraints: Optional[Dict[str, Any]] = None,
    function_role: Optional[str] = None,
    name_patterns: Optional[List[str]] = None,
    limit_results: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Find IFC elements based on multiple criteria and extract their properties.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        element_type (Optional[str]): IFC element type to filter by (e.g., 'IfcDoor', 'IfcWall', 'IfcSpace')
        property_names (Optional[List[str]]): List of property names to extract from found elements
        pset_names (Optional[List[str]]): List of property set names to search within for property extraction
        filter_criteria (Optional[Dict[str, Any]]): Dictionary of property name-value pairs to filter elements by. 
            Elements must match all specified criteria.
        spatial_constraints (Optional[Dict[str, Any]]): Dictionary specifying spatial relationships, such as:
            - "in_storey": Name or entity of IfcBuildingStorey
            - "in_space": Name or entity of IfcSpace
            - "on_level": Level name
        function_role (Optional[str]): Functional role for certain element types (e.g., 'main entrance' for doors, 
            'exterior' for walls)
        name_patterns (Optional[List[str]]): List of regex patterns to match against element names
        limit_results (Optional[int]): Maximum number of results to return
        
    Returns:
        List[Dict[str, Any]]: List of dictionaries, each containing:
            - element_name: The element's name
            - element_guid: The element's GlobalId
            - element_type: The IFC type of the element
            - properties: Dictionary mapping property names to their values (for requested properties)
            - spatial_info: Dictionary with spatial relationship information
            - function_role: Functional role if specified and applicable
    """
    # Load the IFC file
    ifc_file = ifcopenshell.open(ifc_file_path)
    
    # Start with all elements or filter by element_type
    if element_type:
        elements = ifc_file.by_type(element_type)
    else:
        elements = ifc_file.by_type("IfcProduct")  # Get all product elements
    
    # Convert to list for further filtering
    elements = list(elements)
    
    # Apply name pattern matching if provided
    if name_patterns:
        filtered_elements = []
        for element in elements:
            element_name = element.Name if element.Name else ""
            for pattern in name_patterns:
                if re.search(pattern, element_name, re.IGNORECASE):
                    filtered_elements.append(element)
                    break
        elements = filtered_elements
    
    # Apply spatial constraints if provided
    if spatial_constraints:
        filtered_elements = []
        for element in elements:
            container = ifcopenshell.util.element.get_container(element)
            if container:
                # Check if element matches spatial constraints
                match = True
                
                # Check "in_storey" constraint
                if "in_storey" in spatial_constraints:
                    storey_constraint = spatial_constraints["in_storey"]
                    if isinstance(storey_constraint, str):
                        # Match by storey name
                        if container.Name != storey_constraint:
                            match = False
                    else:
                        # Match by storey entity
                        if container != storey_constraint:
                            match = False
                
                if match:
                    filtered_elements.append(element)
            
        elements = filtered_elements
    
    # Apply function role filtering for specific element types
    if function_role and element_type == "IfcDoor":
        filtered_elements = []
        for element in elements:
            # For doors, check if they match the function role
            # This is a simplified implementation - in practice, this would be more complex
            psets = ifcopenshell.util.element.get_psets(element)
            
            # Check if any property indicates this door matches the function role
            role_match = False
            for pset_dict in psets.values():
                for prop_name, prop_value in pset_dict.items():
                    if isinstance(prop_value, str) and function_role.lower() in prop_value.lower():
                        role_match = True
                        break
                if role_match:
                    break
            
            if role_match:
                filtered_elements.append(element)
        
        elements = filtered_elements
    
    # Apply filter criteria if provided
    if filter_criteria:
        filtered_elements = []
        for element in elements:
            psets = ifcopenshell.util.element.get_psets(element)
            match = True
            
            # Check if element matches all filter criteria
            for filter_prop, filter_value in filter_criteria.items():
                prop_found = False
                
                # Search for the property in all psets
                for pset_dict in psets.values():
                    if filter_prop in pset_dict:
                        prop_value = pset_dict[filter_prop]
                        if prop_value == filter_value:
                            prop_found = True
                            break
                
                if not prop_found:
                    match = False
                    break
            
            if match:
                filtered_elements.append(element)
        
        elements = filtered_elements
    
    # Extract properties for each element
    results = []
    for element in elements:
        # Get element properties using ifcopenshell utilities
        psets = ifcopenshell.util.element.get_psets(element)
        
        # Extract requested properties
        element_properties = {}
        if property_names:
            for prop_name in property_names:
                # Look for property in all psets or specified psets
                found = False
                if pset_names:
                    # Search only in specified psets
                    for pset_name in pset_names:
                        if pset_name in psets and prop_name in psets[pset_name]:
                            element_properties[prop_name] = psets[pset_name][prop_name]
                            found = True
                            break
                else:
                    # Search in all psets
                    for pset_dict in psets.values():
                        if prop_name in pset_dict:
                            element_properties[prop_name] = pset_dict[prop_name]
                            found = True
                            break
                
                # If not found, set to None
                if not found:
                    element_properties[prop_name] = None
        
        # Get spatial information
        spatial_info = {}
        container = ifcopenshell.util.element.get_container(element)
        if container:
            spatial_info["container_name"] = container.Name if container.Name else "Unnamed"
            spatial_info["container_type"] = container.is_a()
        
        result = {
            "element_name": element.Name if element.Name else "Unnamed",
            "element_guid": element.GlobalId,
            "element_type": element.is_a(),
            "properties": element_properties,
            "spatial_info": spatial_info,
            "function_role": function_role
        }
        results.append(result)
    
    # Apply limit if specified
    if limit_results:
        results = results[:limit_results]
    
    return results