import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional
import re

def find_entities_by_classification_and_properties(
    model_path: str,
    name_patterns: Optional[List[str]] = None,
    entity_types: Optional[List[str]] = None,
    property_filters: Optional[Dict[str, Any]] = None,
    container_types: Optional[List[str]] = None,
    match_mode: str = "substring",
    classification_keywords: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Search for IFC entities based on multiple criteria in a single call.
    
    This function searches for entities across multiple IFC entity types simultaneously,
    with filtering by name patterns, property values, and classification keywords.
    
    Args:
        model_path (str): Path to the IFC model file
        name_patterns (List[str], optional): List of name patterns to search for (default: None)
        entity_types (List[str], optional): List of IFC entity types to search (default: None, meaning all types)
        property_filters (Dict[str, Any], optional): Dictionary of property name -> value pairs for filtering (default: None)
        container_types (List[str], optional): List of container types to search in (default: ["IfcSpace"])
        match_mode (str): Matching mode - "substring", "exact", or "regex" (default: "substring")
        classification_keywords (List[str], optional): Keywords to search in classification property sets (default: None)
        
    Returns:
        List[Dict[str, Any]]: List of matching entities with comprehensive information
        
    Note:
        This function works with IFC models from various BIM authoring software and handles 
        standard property set conventions like PSet_Revit_* for Revit-exported models.
    """
    # Set default values
    if container_types is None:
        container_types = ["IfcSpace"]
    if classification_keywords is None:
        classification_keywords = []
    
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
        matching_pattern = None
        if name_patterns is not None and len(name_patterns) > 0:
            name_match = False
            for pattern in name_patterns:
                if match_mode == "substring" and pattern.lower() in entity_name.lower():
                    name_match = True
                    matching_pattern = pattern
                    break
                elif match_mode == "exact" and pattern == entity_name:
                    name_match = True
                    matching_pattern = pattern
                    break
                elif match_mode == "regex":
                    try:
                        if re.search(pattern, entity_name, re.IGNORECASE):
                            name_match = True
                            matching_pattern = pattern
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
        matching_property = None
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
                            matching_property = prop_name
                            found_property = True
                            break
                        # Also try case-insensitive comparison for strings
                        elif isinstance(entity_prop_value, str) and isinstance(prop_value, str):
                            if entity_prop_value.lower() == prop_value.lower():
                                property_match = True
                                matching_property = prop_name
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
            # Check if any classification keyword is found in property set names or values
            for keyword in classification_keywords:
                keyword_lower = keyword.lower()
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
            
        # Get container information
        container_name = None
        container_type = None
        try:
            container = ifcopenshell.util.element.get_container(entity)
            if container:
                container_name = getattr(container, "Name", None) or "Unnamed"
                container_type = container.is_a()
        except Exception as e:
            pass
        
        # Determine matching criteria for the result
        matching_criteria = []
        if matching_pattern:
            matching_criteria.append(f"name_pattern: {matching_pattern}")
        if matching_property:
            matching_criteria.append(f"property: {matching_property}")
        if classification_keywords and len(classification_keywords) > 0 and classification_match:
            matching_criteria.append("classification_keyword_matched")
        
        # Add to results
        results.append({
            "entity_name": entity_name,
            "entity_type": entity_type,
            "entity_guid": entity.GlobalId,
            "entity_properties": entity_properties,
            "container_name": container_name,
            "container_type": container_type,
            "matching_criteria": matching_criteria
        })
    
    return results