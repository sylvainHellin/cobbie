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
from typing import List, Dict, Any, Optional


def find_and_get_element_dimensions(
    model_path: str,
    dimension_names: List[str],
    name_patterns: Optional[List[str]] = None,
    entity_types: Optional[List[str]] = None,
    property_filters: Optional[Dict[str, Any]] = None,
    match_mode: str = "substring"
) -> List[Dict[str, Any]]:
    """
    Search for IFC elements based on name patterns and extract specified dimensional properties.
    
    This function combines element searching with dimensional property extraction, using
    enhanced property mapping for common dimensional terms. It supports various matching
    modes and filtering options.
    
    Args:
        model_path (str): Path to the IFC model file
        dimension_names (List[str]): List of dimensional property names to retrieve.
            Common properties include: "Width", "Height", "Thickness", "Depth", "Length", 
            "Volume", "Area", "FlangeWidth", "WebThickness", etc.
        name_patterns (List[str], optional): List of name patterns to search for (case-insensitive)
        entity_types (List[str], optional): List of IFC entity types to search within
        property_filters (Dict[str, Any], optional): Dictionary of property name -> value pairs for additional filtering
        match_mode (str): Matching mode - "substring", "exact", or "regex" (default: "substring")
        
    Returns:
        List[Dict[str, Any]]: List of dictionaries containing element identification information
                             and dimensional properties
        
    Note:
        This function is specifically designed for IFC models exported from Revit, which use
        standard property set names like PSet_Revit_Dimensions, PSet_Revit_Type_Dimensions, etc.
        It uses a dimension mapping to translate common dimensional terms to technical property names.
    """
    # Mapping of common dimensional terms to technical property names in Revit PSets
    dimension_mapping = {
        # PSet_Revit_Type_Dimensions mappings
        "Width": "bf",  # Flange width
        "FlangeWidth": "bf",
        "Height": "d",  # Depth
        "Depth": "d",
        "WebThickness": "tw",
        "FlangeThickness": "tf",
        "k": "k",  # Distance from outer face of flange to web toe of fillet
        "kr": "kr",  # Root radius
        
        # PSet_Revit_Dimensions mappings
        "Length": "Length",
        "Volume": "Volume",
        
        # PSet_Revit_Type_Structural mappings
        "W": "W",  # Section modulus
        "A": "A",  # Cross-sectional area
        
        # Additional common mappings
        "Area": "A",
        "Thickness": "tf",  # Defaulting to flange thickness for thickness
    }
    
    # Load the IFC model
    try:
        model = ifcopenshell.open(model_path)
    except Exception as e:
        raise FileNotFoundError(f"Could not open IFC model at {model_path}: {str(e)}")
    
    # Get all elements or filter by entity types
    if entity_types:
        elements = []
        for entity_type in entity_types:
            elements.extend(model.by_type(entity_type))
    else:
        elements = model.by_type("IfcElement")
    
    results = []
    
    # Process each element
    for element in elements:
        element_name = element.Name if hasattr(element, 'Name') and element.Name else ""
        
        # If name_patterns is None, we include all elements
        if name_patterns is None:
            name_matches = True
        else:
            # Check if element matches name patterns
            name_matches = False
            for pattern in name_patterns:
                if match_mode == "substring":
                    if pattern.lower() in element_name.lower():
                        name_matches = True
                        break
                elif match_mode == "exact":
                    if pattern.lower() == element_name.lower():
                        name_matches = True
                        break
                elif match_mode == "regex":
                    try:
                        if re.search(pattern, element_name, re.IGNORECASE):
                            name_matches = True
                            break
                    except re.error:
                        # If regex is invalid, skip this pattern
                        continue
            
            if not name_matches:
                continue
            
        # Check property filters if provided
        if property_filters:
            psets = ifcopenshell.util.element.get_psets(element)
            property_match = True
            
            for prop_name, prop_value in property_filters.items():
                found_prop = False
                for pset_name, properties in psets.items():
                    if prop_name in properties and properties[prop_name] == prop_value:
                        found_prop = True
                        break
                
                if not found_prop:
                    property_match = False
                    break
            
            if not property_match:
                continue
        
        # Extract dimensional properties using the enhanced mapping approach
        dimensions = {}
        psets = ifcopenshell.util.element.get_psets(element)
        
        # Process each requested dimension
        for dim_name in dimension_names:
            # Get the technical property name from mapping
            technical_name = dimension_mapping.get(dim_name, dim_name)  # Use dim_name directly if not in mapping
            
            # Search through property sets for the technical property name
            found = False
            for pset_name, properties in psets.items():
                # Skip metadata field
                if "id" in properties:
                    properties = {k: v for k, v in properties.items() if k != "id"}
                
                # Check if the technical property name exists in this property set
                if technical_name in properties:
                    dimensions[dim_name] = properties[technical_name]
                    found = True
                    break
            
            # If not found and the technical name differs from the requested name, 
            # try searching with the original dimension name
            if not found and technical_name != dim_name:
                for pset_name, properties in psets.items():
                    # Skip metadata field
                    if "id" in properties:
                        properties = {k: v for k, v in properties.items() if k != "id"}
                    
                    # Check if the original dimension name exists in this property set
                    if dim_name in properties:
                        dimensions[dim_name] = properties[dim_name]
                        found = True
                        break
            
            # If still not found, try case-insensitive matching
            if not found:
                for pset_name, properties in psets.items():
                    # Skip metadata field
                    if "id" in properties:
                        properties = {k: v for k, v in properties.items() if k != "id"}
                    
                    # Try case-insensitive matching
                    for prop_key, prop_value in properties.items():
                        if prop_key.lower() == dim_name.lower():
                            dimensions[dim_name] = prop_value
                            found = True
                            break
                    if found:
                        break
        
        # Get container information
        container = ifcopenshell.util.element.get_container(element)
        container_info = {}
        if container:
            container_info["name"] = container.Name if hasattr(container, 'Name') and container.Name else None
            container_info["type"] = container.is_a() if container else None
            container_info["guid"] = container.GlobalId if hasattr(container, 'GlobalId') else None
        
        # Determine matching criteria
        matching_criteria = {}
        if name_patterns:
            matching_criteria["name_pattern"] = name_patterns
            matching_criteria["match_mode"] = match_mode
        if entity_types:
            matching_criteria["entity_types"] = entity_types
        if property_filters:
            matching_criteria["property_filters"] = property_filters
        
        # Add result
        results.append({
            "element_name": element_name,
            "element_guid": element.GlobalId,
            "element_type": element.is_a(),
            "dimensions": dimensions,
            "container_info": container_info,
            "matching_criteria": matching_criteria
        })
    
    return results