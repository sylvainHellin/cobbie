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
from typing import List, Dict, Any, Optional, Union

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
    Search for IFC elements based on multiple criteria and extract specific property values.
    
    This function works with IFC models from various BIM authoring software including Revit
    (handling PSet_Revit_* property sets) and other software that follows standard IFC conventions.
    
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
        List[Dict[str, Any]]: List of dictionaries containing element information and properties
        
    Example:
        >>> results = find_and_extract_element_properties(
        ...     model_path="model.ifc",
        ...     property_names=["LoadBearing", "FireRating"],
        ...     name_patterns=["Wall", "Partition"],
        ...     entity_types=["IfcWall", "IfcWallStandardCase"],
        ...     property_filters={"LoadBearing": True},
        ...     match_mode="substring"
        ... )
    """
    
    # Load the model
    try:
        model = ifcopenshell.open(model_path)
    except Exception as e:
        raise FileNotFoundError(f"Could not load model from {model_path}: {str(e)}")
    
    # Get all elements to process
    if entity_types:
        elements = []
        for entity_type in entity_types:
            elements.extend(model.by_type(entity_type))
    else:
        # If no entity types specified, get all elements that have representations
        elements = []
        for element in model:
            if hasattr(element, "Representation") and element.Representation:
                elements.append(element)
    
    # Filter elements based on criteria
    filtered_elements = []
    
    for element in elements:
        should_include = True
        matching_criteria = []
        
        # Filter by name patterns
        if name_patterns:
            name_match = False
            element_name = getattr(element, "Name", None) or ""
            
            for pattern in name_patterns:
                if match_mode == "exact" and element_name == pattern:
                    name_match = True
                    matching_criteria.append(f"name_exact:{pattern}")
                    break
                elif match_mode == "substring" and pattern in element_name:
                    name_match = True
                    matching_criteria.append(f"name_substring:{pattern}")
                    break
                elif match_mode == "regex":
                    try:
                        if re.search(pattern, element_name):
                            name_match = True
                            matching_criteria.append(f"name_regex:{pattern}")
                            break
                    except re.error:
                        # Invalid regex, skip this pattern
                        continue
            
            if not name_match:
                should_include = False
        
        # Filter by property values
        if should_include and property_filters:
            element_psets = ifcopenshell.util.element.get_psets(element)
            property_match = True
            
            for filter_prop_name, filter_prop_value in property_filters.items():
                found_prop = False
                
                # Search in all property sets
                for pset_name, pset_props in element_psets.items():
                    if filter_prop_name in pset_props:
                        found_prop = True
                        # Check if property value matches
                        if pset_props[filter_prop_name] == filter_prop_value:
                            matching_criteria.append(f"property:{filter_prop_name}={filter_prop_value}")
                        else:
                            property_match = False
                        break
                
                if not found_prop:
                    property_match = False
            
            if not property_match:
                should_include = False
        
        # Filter by classification keywords
        if should_include and classification_keywords:
            element_psets = ifcopenshell.util.element.get_psets(element)
            classification_match = False
            
            # Look for classification-related property sets (broadened definition)
            for keyword in classification_keywords:
                keyword_lower = keyword.lower()
                for pset_name, pset_props in element_psets.items():
                    pset_name_lower = pset_name.lower()
                    # Check if this is a classification property set (PSet_*, Pset_*, or contains "classification")
                    is_classification_pset = (
                        pset_name.startswith("PSet_") or 
                        pset_name.startswith("Pset_") or 
                        "classification" in pset_name_lower
                    )
                    
                    if is_classification_pset:
                        # Check if keyword is in property set name or any property names/values
                        if keyword_lower in pset_name_lower:
                            classification_match = True
                            matching_criteria.append(f"classification_pset:{keyword}")
                            break
                        
                        # Check property names and values
                        for prop_name, prop_value in pset_props.items():
                            prop_name_lower = prop_name.lower()
                            # Check if keyword is in property name
                            if keyword_lower in prop_name_lower:
                                classification_match = True
                                matching_criteria.append(f"classification_prop_name:{keyword}")
                                break
                            # Check if keyword is in property value (for string values)
                            if isinstance(prop_value, str) and keyword_lower in prop_value.lower():
                                classification_match = True
                                matching_criteria.append(f"classification_prop_value:{keyword}")
                                break
                            # Check if keyword matches property value exactly (for non-string values)
                            elif str(prop_value).lower() == keyword_lower:
                                classification_match = True
                                matching_criteria.append(f"classification_prop_value:{keyword}")
                                break
                    
                    if classification_match:
                        break
                if classification_match:
                    break
            
            if not classification_match:
                should_include = False
        
        # Filter by container types
        if should_include and container_types:
            container = ifcopenshell.util.element.get_container(element)
            if container:
                container_type = container.is_a()
                if container_type not in container_types:
                    should_include = False
                else:
                    matching_criteria.append(f"container_type:{container_type}")
            else:
                should_include = False
        
        # If all filters pass, include this element
        if should_include:
            filtered_elements.append({
                "element": element,
                "matching_criteria": matching_criteria
            })
    
    # Extract properties for filtered elements
    results = []
    
    for item in filtered_elements:
        element = item["element"]
        matching_criteria = item["matching_criteria"]
        
        # Get element basic information
        element_name = getattr(element, "Name", None) or ""
        element_guid = getattr(element, "GlobalId", "")
        element_type = element.is_a()
        
        # Get container information
        container_name = ""
        container_type = ""
        container = ifcopenshell.util.element.get_container(element)
        if container:
            container_name = getattr(container, "Name", None) or ""
            container_type = container.is_a()
        
        # Extract requested properties
        element_psets = ifcopenshell.util.element.get_psets(element)
        extracted_properties = {}
        
        for prop_name in property_names:
            found = False
            # Search in all property sets for the requested property
            for pset_name, pset_props in element_psets.items():
                if prop_name in pset_props:
                    extracted_properties[prop_name] = pset_props[prop_name]
                    found = True
                    break
            
            # If not found, mark as None
            if not found:
                extracted_properties[prop_name] = None
        
        # Create result dictionary
        result = {
            "element_name": element_name,
            "element_guid": element_guid,
            "element_type": element_type,
            "properties": extracted_properties,
            "container_name": container_name,
            "container_type": container_type,
            "matching_criteria": matching_criteria
        }
        
        results.append(result)
    
    return results