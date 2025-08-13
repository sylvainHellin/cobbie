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
from typing import List, Dict, Any, Union

def advanced_entity_search_with_filters(
    model_path: str,
    name_patterns: List[str],
    entity_types: List[str] = None,
    container_types: List[str] = None,
    property_filters: Dict[str, Any] = None,
    match_mode: str = "substring"
) -> List[Dict[str, Any]]:
    """
    Advanced search for IFC entities with multiple filtering options.
    
    This function provides powerful search capabilities for IFC entities with support for:
    - Multi-type entity search across different IFC entity types
    - Flexible name pattern matching (substring, exact, regex)
    - Multi-container lookup for spatial structure containment
    - Property-based filtering using property sets
    - Enhanced output with detailed entity information
    
    The function works with IFC models exported from various BIM authoring software,
    including Revit (PSet_Revit_* property sets), ArchiCAD, and others.
    
    Args:
        model_path: Path to the IFC model file
        name_patterns: List of name patterns to search for
        entity_types: List of IFC entity types to search (None means all types)
        container_types: List of container types to search in (None means default spatial containers)
        property_filters: Dictionary of property name -> value pairs for filtering
        match_mode: Matching mode - "substring", "exact", or "regex"
        
    Returns:
        List of dictionaries containing entity information and matching criteria:
        - entity_name: Name of the found entity
        - entity_type: Type of the found entity
        - entity_guid: GlobalId of the entity
        - entity_properties: Dictionary of all properties from property sets
        - container_name: Name of the containing spatial structure (if found)
        - container_type: Type of the containing spatial structure (if found)
        - matching_criteria: Information about why this entity matched (which pattern, property, etc.)
        
    Example:
        # Find all walls with "Wall" in their name
        result = advanced_entity_search_with_filters(
            model_path="model.ifc",
            name_patterns=["Wall"],
            entity_types=["IfcWall"],
            match_mode="substring"
        )
        
        # Find load-bearing walls using property filtering
        result = advanced_entity_search_with_filters(
            model_path="model.ifc",
            name_patterns=["Wall"],
            entity_types=["IfcWall"],
            property_filters={"LoadBearing": True}
        )
        
        # Find rooms and spaces with exact name matching
        result = advanced_entity_search_with_filters(
            model_path="model.ifc",
            name_patterns=["Conference Room"],
            entity_types=["IfcSpace", "IfcRoom"],
            match_mode="exact"
        )
    """
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Get all relevant entities based on entity_types
    if entity_types is None:
        # If no specific types provided, get all products
        entities = model.by_type("IfcProduct")
    else:
        entities = []
        for entity_type in entity_types:
            try:
                entities.extend(model.by_type(entity_type))
            except Exception:
                # Skip invalid entity types
                continue
    
    # Default container types if not specified
    if container_types is None:
        container_types = ["IfcBuildingStorey", "IfcSpace", "IfcSite", "IfcBuilding"]
    
    # Get all containers
    containers = []
    for container_type in container_types:
        try:
            containers.extend(model.by_type(container_type))
        except Exception:
            # Skip invalid container types
            continue
    
    # Create a mapping of entities to their containers
    entity_to_container = {}
    
    # For each container, find contained entities
    for container in containers:
        try:
            contained_entities = ifcopenshell.util.element.get_contained(container)
            for entity in contained_entities:
                entity_to_container[entity] = container
        except Exception:
            # Some containers might not support get_contained
            continue
    
    # Also check referenced structures
    for entity in entities:
        if entity not in entity_to_container:
            try:
                referenced_structures = ifcopenshell.util.element.get_referenced_structures(entity)
                if referenced_structures:
                    entity_to_container[entity] = referenced_structures[0]  # Take first if multiple
            except Exception:
                continue
    
    results = []
    
    # Process each entity
    for entity in entities:
        # Get entity name
        entity_name = getattr(entity, 'Name', None) or ''
        
        # Check if entity name matches any pattern
        name_matches = []
        match = False
        if match_mode == "substring":
            for pattern in name_patterns:
                if pattern.lower() in entity_name.lower():
                    name_matches.append({"pattern": pattern, "mode": "substring"})
            match = len(name_matches) > 0
        elif match_mode == "exact":
            for pattern in name_patterns:
                if pattern.lower() == entity_name.lower():
                    name_matches.append({"pattern": pattern, "mode": "exact"})
            match = len(name_matches) > 0
        elif match_mode == "regex":
            for pattern in name_patterns:
                try:
                    if re.search(pattern, entity_name, re.IGNORECASE):
                        name_matches.append({"pattern": pattern, "mode": "regex"})
                except re.error:
                    # Invalid regex pattern
                    continue
            match = len(name_matches) > 0
        
        # If no name match, skip this entity
        if not match:
            continue
            
        # Get entity properties
        try:
            entity_properties = ifcopenshell.util.element.get_psets(entity)
        except Exception:
            entity_properties = {}
        
        # Check property filters if provided
        property_matches = []
        if property_filters:
            matches_all_filters = True
            for prop_name, prop_value in property_filters.items():
                found_match = False
                # Search for property in all property sets
                for pset_name, pset_props in entity_properties.items():
                    if prop_name in pset_props and pset_props[prop_name] == prop_value:
                        property_matches.append({
                            "property_set": pset_name,
                            "property_name": prop_name,
                            "property_value": prop_value
                        })
                        found_match = True
                        break
                
                if not found_match:
                    matches_all_filters = False
                    break
            
            # If property filters don't match, skip this entity
            if not matches_all_filters:
                continue
        
        # Get container information
        container = entity_to_container.get(entity)
        container_name = getattr(container, 'Name', None) if container else None
        container_type = container.is_a() if container else None
        
        # Create result entry
        result_entry = {
            "entity_name": entity_name,
            "entity_type": entity.is_a(),
            "entity_guid": getattr(entity, 'GlobalId', None),
            "entity_properties": entity_properties,
            "container_name": container_name,
            "container_type": container_type,
            "matching_criteria": {
                "name_matches": name_matches,
                "property_matches": property_matches
            }
        }
        
        results.append(result_entry)
    
    return results