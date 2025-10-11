import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Optional

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
    The function handles both standard spatial containment relationships (IfcRelContainedInSpatialStructure)
    and aggregation relationships (IfcRelAggregates) that are sometimes used in IFC models exported from
    various BIM authoring software.
    
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
        container = None
        
        try:
            # First, try the standard method using IfcOpenShell's utility
            container = ifcopenshell.util.element.get_container(
                entity, 
                ifc_class=container_type
            )
            
            # If no container of the specified type is found, try to get any container
            if container is None:
                container = ifcopenshell.util.element.get_container(entity)
            
            # If still no container found, try aggregation relationships (IfcRelAggregates)
            if container is None:
                container = _find_container_via_aggregation(entity, container_type, model)
            
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

def _find_container_via_aggregation(entity, container_type: str, model) -> Optional[object]:
    """
    Helper function to find container via IfcRelAggregates relationships.
    
    This function handles cases where entities are related to their containers
    through aggregation relationships rather than standard spatial containment.
    This is common in some IFC models exported from certain BIM software.
    
    Args:
        entity: The IFC entity to find the container for
        container_type: The desired container type (e.g., "IfcBuildingStorey")
        model: The IFC model object
        
    Returns:
        The container entity if found, None otherwise
    """
    # Check if the entity has Decomposes relationship (IfcRelAggregates)
    if hasattr(entity, 'Decomposes') and entity.Decomposes:
        for decomposes_rel in entity.Decomposes:
            if hasattr(decomposes_rel, 'RelatingObject'):
                relating_object = decomposes_rel.RelatingObject
                # Check if this matches our desired container type
                if relating_object.is_a() == container_type:
                    return relating_object
                # If we're looking for any container and this is a spatial structure
                elif container_type == "IfcSpace" and relating_object.is_a() in ["IfcBuildingStorey", "IfcBuilding", "IfcSite"]:
                    return relating_object
    
    # If not found via Decomposes, search all IfcRelAggregates relationships
    # where this entity might be a RelatedObject
    for rel_aggregates in model.by_type("IfcRelAggregates"):
        if hasattr(rel_aggregates, 'RelatedObjects') and hasattr(rel_aggregates, 'RelatingObject'):
            # Check if our entity is in the RelatedObjects
            if entity in rel_aggregates.RelatedObjects:
                relating_object = rel_aggregates.RelatingObject
                # Check if this matches our desired container type
                if relating_object.is_a() == container_type:
                    return relating_object
                # If we're looking for any container and this is a spatial structure
                elif container_type == "IfcSpace" and relating_object.is_a() in ["IfcBuildingStorey", "IfcBuilding", "IfcSite"]:
                    return relating_object
    
    return None