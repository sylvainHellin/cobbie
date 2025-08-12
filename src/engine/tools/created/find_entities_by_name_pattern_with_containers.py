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

def find_entities_by_name_pattern_with_containers(
    model_path: str,
    name_pattern: str,
    entity_type: str = "IfcElement",
    container_type: str = "IfcSpace"
) -> List[Dict[str, str]]:
    """
    Find IFC entities based on name patterns and return information about their containing spatial structures.
    
    This function searches for IFC entities whose names contain the specified pattern (case-insensitive substring match).
    For each matching entity, it determines the spatial structure that contains the entity (e.g., IfcSpace, IfcBuildingStorey).
    
    Args:
        model_path (str): The file path to the IFC model
        name_pattern (str): The pattern to search for in entity names (case-insensitive substring search)
        entity_type (str, optional): The IFC entity type to search within. Defaults to "IfcElement" to search all building elements.
        container_type (str, optional): The type of spatial container to look for. Defaults to "IfcSpace".
        
    Returns:
        List[Dict[str, str]]: List of dictionaries containing:
            - entity_name: Name of the found entity
            - entity_type: Type of the found entity
            - container_name: Name of the containing spatial structure
            - container_type: Type of the containing spatial structure
            
    Example:
        >>> results = find_entities_by_name_pattern_with_containers(
        ...     "model.ifc", 
        ...     "thermostat", 
        ...     "IfcDistributionControlElement", 
        ...     "IfcSpace"
        ... )
        >>> print(results)
        [{'entity_name': 'Thermostat1', 'entity_type': 'IfcDistributionControlElement', 
          'container_name': 'RoomA', 'container_type': 'IfcSpace'}]
    """
    try:
        # Load the IFC model
        model = ifcopenshell.open(model_path)
    except Exception as e:
        raise FileNotFoundError(f"Could not open IFC model at {model_path}: {str(e)}")
    
    try:
        # Search for entities of the specified type
        entities = model.by_type(entity_type)
    except Exception as e:
        raise ValueError(f"Invalid entity_type '{entity_type}': {str(e)}")
    
    # Filter entities by name pattern (case-insensitive)
    name_pattern_lower = name_pattern.lower()
    matching_entities = [
        entity for entity in entities 
        if hasattr(entity, 'Name') and entity.Name and name_pattern_lower in entity.Name.lower()
    ]
    
    # Prepare results
    results = []
    
    # For each matching entity, find its container
    for entity in matching_entities:
        try:
            # Get the container of the entity with the specified type
            container = ifcopenshell.util.element.get_container(
                entity, 
                ifc_class=container_type
            )
            
            # If no container of the specified type is found, try to get any container
            if container is None:
                container = ifcopenshell.util.element.get_container(entity)
            
            # Add to results
            results.append({
                "entity_name": entity.Name if hasattr(entity, 'Name') and entity.Name else "Unnamed",
                "entity_type": entity.is_a(),
                "container_name": container.Name if container and hasattr(container, 'Name') and container.Name else None,
                "container_type": container.is_a() if container else None
            })
        except Exception:
            # Skip entities that cause errors during processing
            continue
    
    return results