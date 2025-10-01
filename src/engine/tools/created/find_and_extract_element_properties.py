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
import re


def find_and_extract_element_properties(
    model_path: str,
    property_names: List[str],
    name_patterns: Optional[List[str]] = None,
    entity_types: Optional[List[str]] = None,
    property_filters: Optional[Dict[str, Any]] = None,
    classification_keywords: Optional[List[str]] = None,
    match_mode: str = "substring",
    container_types: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Search for IFC entities based on multiple criteria and extract specific property values.
    
    This function works with IFC models from various BIM authoring software and handles
    standard property set conventions like PSet_Revit_* for Revit-exported models.
    
    Args:
        model_path (str): Path to the IFC model file
        property_names (List[str]): List of specific property names to extract
        name_patterns (List[str], optional): List of name patterns to search for
        entity_types (List[str], optional): List of IFC entity types to search
        property_filters (Dict[str, Any], optional): Dictionary of property name -> value pairs for filtering
        classification_keywords (List[str], optional): Keywords to search in classification property sets
        match_mode (str): Matching mode - "substring", "exact", or "regex" (default: "substring")
        container_types (List[str], optional): List of container types to search in
        
    Returns:
        List[Dict[str, Any]]: List of dictionaries containing element information and properties:
            - element_name: Name of the found element
            - element_guid: GlobalId of the element
            - element_type: IFC type of the element
            - container_info: Spatial container information (if available)
            - properties: Dictionary of requested property names and their values
    """
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Define common property mappings for different software
    property_mappings = {
        "Width": ["Width", "NominalWidth"],
        "Height": ["Height", "NominalHeight"],
        "Length": ["Length", "NominalLength"],
        "Area": ["Area", "GrossArea", "NetArea"],
        "Volume": ["Volume", "GrossVolume", "NetVolume"],
        "FireRating": ["FireRating", "Fire Resistance Rating"],
        "ThermalTransmittance": ["ThermalTransmittance", "U-Value", "Heat Transfer Coefficient"],
        "Description": ["Description"],
        "Name": ["Name"]
    }
    
    # Get all relevant elements
    if entity_types:
        elements = []
        for entity_type in entity_types:
            elements.extend(model.by_type(entity_type))
    else:
        # Get all IfcProduct entities (includes IfcElement, IfcSpatialElement, etc.)
        elements = model.by_type("IfcProduct")
    
    # Filter by entity types if specified
    if entity_types:
        elements = [e for e in elements if e.is_a() in entity_types]
    
    # Filter by name patterns if specified
    if name_patterns:
        filtered_elements = []
        for element in elements:
            element_name = getattr(element, 'Name', '') or ''
            match_found = False
            for pattern in name_patterns:
                if match_mode == "exact" and element_name == pattern:
                    match_found = True
                    break
                elif match_mode == "substring" and pattern in element_name:
                    match_found = True
                    break
                elif match_mode == "regex":
                    try:
                        if re.search(pattern, element_name):
                            match_found = True
                            break
                    except re.error:
                        # Invalid regex, skip
                        pass
            if match_found:
                filtered_elements.append(element)
        elements = filtered_elements
    
    # Filter by property filters if specified
    if property_filters:
        filtered_elements = []
        for element in elements:
            psets = ifcopenshell.util.element.get_psets(element)
            match_all_filters = True
            for filter_prop, filter_value in property_filters.items():
                prop_found = False
                # Check direct attributes first
                if hasattr(element, filter_prop):
                    if getattr(element, filter_prop) == filter_value:
                        prop_found = True
                
                # If not found in direct attributes, search in property sets
                if not prop_found:
                    # Search for the property in all property sets
                    for pset_name, properties in psets.items():
                        # Check for exact match first
                        if filter_prop in properties:
                            if properties[filter_prop] == filter_value:
                                prop_found = True
                                break
                        # Check for mapped property names
                        elif filter_prop in property_mappings:
                            for mapped_name in property_mappings[filter_prop]:
                                if mapped_name in properties:
                                    if properties[mapped_name] == filter_value:
                                        prop_found = True
                                        break
                            if prop_found:
                                break
                
                if not prop_found:
                    match_all_filters = False
                    break
            if match_all_filters:
                filtered_elements.append(element)
        elements = filtered_elements
    
    # Filter by classification keywords if specified
    if classification_keywords:
        filtered_elements = []
        for element in elements:
            psets = ifcopenshell.util.element.get_psets(element)
            keyword_found = False
            for keyword in classification_keywords:
                # Look for classification-related properties
                for pset_name, properties in psets.items():
                    if 'Classification' in pset_name or 'Identity' in pset_name:
                        for prop_name, prop_value in properties.items():
                            if isinstance(prop_value, str) and keyword.lower() in prop_value.lower():
                                keyword_found = True
                                break
                    if keyword_found:
                        break
                if keyword_found:
                    break
            if keyword_found:
                filtered_elements.append(element)
        elements = filtered_elements
    
    # Filter by container types if specified
    if container_types:
        filtered_elements = []
        for element in elements:
            container = ifcopenshell.util.element.get_container(element)
            if container and container.is_a() in container_types:
                filtered_elements.append(element)
        elements = filtered_elements
    
    # Extract information and properties for each matching element
    results = []
    for element in elements:
        # Get element basic information
        element_info = {
            "element_name": getattr(element, 'Name', 'N/A') or 'N/A',
            "element_guid": element.GlobalId,
            "element_type": element.is_a()
        }
        
        # Get container information
        container = ifcopenshell.util.element.get_container(element)
        if container:
            element_info["container_info"] = {
                "name": getattr(container, 'Name', 'N/A') or 'N/A',
                "type": container.is_a()
            }
        else:
            element_info["container_info"] = None
        
        # Extract requested properties
        element_info["properties"] = {}
        psets = ifcopenshell.util.element.get_psets(element)
        
        for prop_name in property_names:
            prop_value = None
            
            # Check if it's a direct attribute of the element
            if hasattr(element, prop_name):
                prop_value = getattr(element, prop_name)
            else:
                # Search for the property in all property sets
                found = False
                # Check for exact match first
                for pset_name, properties in psets.items():
                    if prop_name in properties:
                        prop_value = properties[prop_name]
                        found = True
                        break
                
                # If not found, check for mapped property names
                if not found and prop_name in property_mappings:
                    for mapped_name in property_mappings[prop_name]:
                        for pset_name, properties in psets.items():
                            if mapped_name in properties:
                                prop_value = properties[mapped_name]
                                found = True
                                break
                        if found:
                            break
                
                # Special handling for common properties in Revit property sets
                if not found:
                    for pset_name, properties in psets.items():
                        # Check in PSet_Revit_* property sets
                        if 'Revit' in pset_name:
                            # Handle case where property name might be part of a longer name
                            for p_name, p_value in properties.items():
                                if prop_name.lower() in p_name.lower():
                                    prop_value = p_value
                                    found = True
                                    break
                        if found:
                            break
            
            element_info["properties"][prop_name] = prop_value
        
        results.append(element_info)
    
    return results