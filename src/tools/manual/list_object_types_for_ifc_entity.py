# ifcopenshell
import ifcopenshell

def list_object_types_for_ifc_entity(model_path: str, entity_type: str | None = None) -> str:
    """Gets all unique types/categories found for a given IFC entity class in the model.

    Args:
        model_path (str): Absolute path to the IFC model file to analyze.
        entity_type (str, optional): The IFC entity class to search for (e.g. 'IfcFlowSegment', 'IfcWall')
            
    Returns:
        str: A formatted string listing all unique types found, including:
            - Total count of entities
            - List of unique types with their counts
            - Error message if no entities found or invalid entity type
    """
    if not entity_type:
        return "No entity type specified"
    
    ifc_model = ifcopenshell.open(model_path)
    
    try:
        # Get all entities of the specified type
        entities = ifc_model.by_type(entity_type)
        if not entities:
            return f"No entities of type {entity_type} found in model"
        
        # Dictionary to store type counts
        type_counts = {}
        
        # Count occurrences of each type
        for entity in entities:
            object_type = getattr(entity, "ObjectType", None)
            if object_type:
                type_counts[object_type] = type_counts.get(object_type, 0) + 1
        
        if not type_counts:
            return f"No type information found for {entity_type} entities"
        
        # Format output
        output = [f"Types found for {entity_type} (Total entities: {len(entities)}):"]
        
        # Sort types by count (descending) and then alphabetically
        sorted_types = sorted(type_counts.items(), key=lambda x: (-x[1], x[0]))
        
        for type_info, count in sorted_types:
            output.append(f"- {type_info}: {count} instances")
        
        return "\n".join(output)
        
    except Exception as e:
        return f"Error getting entity types: {str(e)}" 