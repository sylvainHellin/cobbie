import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional
import re


def find_elements_with_properties(
    model_path: str,
    property_names: List[str],
    name_patterns: Optional[List[str]] = None,
    entity_types: Optional[List[str]] = None,
    property_filters: Optional[Dict[str, Any]] = None,
    match_mode: str = "substring",
    classification_keywords: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Search for IFC entities based on multiple criteria and extract specific property values.
    
    This function combines search capabilities with property extraction in a single call,
    making it efficient for workflows that need both element identification and specific property values.
    
    Args:
        model_path (str): Path to the IFC model file
        property_names (List[str]): List of specific property names to extract
        name_patterns (List[str], optional): List of name patterns to search for
        entity_types (List[str], optional): List of IFC entity types to search
        property_filters (Dict[str, Any], optional): Dictionary of property name -> value pairs for filtering
        match_mode (str): Matching mode - "substring", "exact", or "regex" (default: "substring")
        classification_keywords (List[str], optional): Keywords to search in classification property sets
        
    Returns:
        List[Dict[str, Any]]: List of dictionaries containing:
            - element_name: Name of the found element
            - element_guid: GlobalId of the element
            - element_type: IFC type of the element
            - container_info: Spatial container information (if available)
            - properties: Dictionary of requested property names and their values
            
    Note:
        This function works with IFC models from various BIM authoring software and handles 
        standard property set conventions like PSet_Revit_* for Revit-exported models.
    """
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Determine which entity types to search
    if entity_types is None:
        # Search all entity types that have GlobalId (IfcRoot and subclasses)
        entities_to_search = model.by_type("IfcRoot")
    else:
        entities_to_search = []
        for entity_type in entity_types:
            entities_to_search.extend(model.by_type(entity_type))
    
    results = []
    
    # Process each entity
    for entity in entities_to_search:
        entity_type = entity.is_a()
        
        # Skip purely relational entities unless specifically requested
        if entity_type.startswith("IfcRel") and entity_types is not None and entity_type not in entity_types:
            continue
            
        # Get entity name
        entity_name = getattr(entity, "Name", None)
        if entity_name is None:
            entity_name = "Unnamed"
        
        # Check name patterns if provided
        name_match = True
        if name_patterns is not None and len(name_patterns) > 0:
            name_match = False
            for pattern in name_patterns:
                if match_mode == "substring" and pattern.lower() in entity_name.lower():
                    name_match = True
                    break
                elif match_mode == "exact" and pattern == entity_name:
                    name_match = True
                    break
                elif match_mode == "regex":
                    try:
                        if re.search(pattern, entity_name, re.IGNORECASE):
                            name_match = True
                            break
                    except re.error:
                        # Invalid regex, skip this pattern
                        continue
            if not name_match:
                continue
        
        # Get all properties for this entity
        try:
            entity_properties = ifcopenshell.util.element.get_psets(entity)
        except Exception as e:
            entity_properties = {}
        
        # Check property filters if provided
        property_match = True
        if property_filters is not None and len(property_filters) > 0:
            property_match = False
            for prop_name, prop_value in property_filters.items():
                # Search for the property in all property sets
                found_property = False
                for pset_name, pset_dict in entity_properties.items():
                    if prop_name in pset_dict:
                        # Handle different data types for comparison
                        entity_prop_value = pset_dict[prop_name]
                        # Convert both values to strings for comparison if needed
                        if str(entity_prop_value) == str(prop_value):
                            property_match = True
                            found_property = True
                            break
                        # Also try case-insensitive comparison for strings
                        elif isinstance(entity_prop_value, str) and isinstance(prop_value, str):
                            if entity_prop_value.lower() == prop_value.lower():
                                property_match = True
                                found_property = True
                                break
                if found_property:
                    break
        
        # If property filters were specified but none matched, skip this entity
        if property_filters is not None and len(property_filters) > 0 and not property_match:
            continue
            
        # Check classification keywords if provided
        classification_match = True
        if classification_keywords and len(classification_keywords) > 0:
            classification_match = False
            # For more precise classification matching, focus on specific property sets and fields
            # that typically contain explicit classifications rather than broad keyword matching
            for keyword in classification_keywords:
                keyword_lower = keyword.lower()
                # Check specific property sets that typically contain classifications
                for pset_name, pset_dict in entity_properties.items():
                    # Focus on property sets that typically contain classifications
                    if any(class_pset in pset_name for class_pset in ["Identity", "Classification", "Category", "Type"]):
                        # Check property names and values in these classification property sets
                        for prop_name, prop_value in pset_dict.items():
                            # Focus on properties that typically contain classifications
                            if any(class_prop in prop_name for class_prop in ["Name", "Category", "Classification", "Type", "Description"]):
                                if isinstance(prop_value, str) and keyword_lower in prop_value.lower():
                                    classification_match = True
                                    break
                    if classification_match:
                        break
                        
                # If not found in specific classification property sets, do a more general search
                # but only as a fallback
                if not classification_match:
                    for pset_name, pset_dict in entity_properties.items():
                        # Check property set names
                        if keyword_lower in pset_name.lower():
                            classification_match = True
                            break
                        # Check property names and values
                        for prop_name, prop_value in pset_dict.items():
                            if keyword_lower in prop_name.lower() or \
                               (isinstance(prop_value, str) and keyword_lower in prop_value.lower()):
                                classification_match = True
                                break
                        if classification_match:
                            break
                if classification_match:
                    break
        
        if not classification_match:
            continue
            
        # Extract requested properties
        element_properties = {}
        for prop_name in property_names:
            found = False
            for pset_name, pset_dict in entity_properties.items():
                if prop_name in pset_dict:
                    element_properties[prop_name] = pset_dict[prop_name]
                    found = True
                    break
            if not found:
                element_properties[prop_name] = None
        
        # Get container information
        container_info = {}
        try:
            container = ifcopenshell.util.element.get_container(entity)
            if container:
                container_info = {
                    "name": getattr(container, "Name", None) or "Unnamed",
                    "type": container.is_a()
                }
        except Exception as e:
            pass
        
        # Add to results
        results.append({
            "element_name": entity_name,
            "element_guid": entity.GlobalId,
            "element_type": entity_type,
            "container_info": container_info,
            "properties": element_properties
        })
    
    return results