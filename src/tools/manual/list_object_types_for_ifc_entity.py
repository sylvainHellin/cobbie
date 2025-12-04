# python packages
import sys
import os
sys.path.insert(0, os.path.dirname(os.getcwd()))

# state management
from state import get_model_path

# ifcopenshell
import ifcopenshell

def list_object_types_for_ifc_entity(model: str = None, entity_type: str = None) -> str:
    """Gets all unique types/categories found for a given IFC entity class in the model.
    
    Args:
        model (str, optional): The type of model to analyze - e.g. 'arc' for architectural 
            or 'mep' for MEP model. If None, uses the model from the current state.
        entity_type (str): The IFC entity class to search for (e.g. 'IfcFlowSegment', 'IfcWall')
            
    Returns:
        str: A formatted string listing all unique types found, including:
            - Total count of entities
            - List of unique types with their counts
            - Error message if no entities found or invalid entity type
    """
    if not entity_type:
        return "No entity type specified"
    
    ifc_model = ifcopenshell.open(get_model_path(model=model))
    
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

if __name__ == "__main__":
    # Test with common entity types
    test_entities = [
        "IfcWall",
        "IfcDoor",
        "IfcWindow",
        "IfcFlowSegment"  # For MEP elements
    ]
    
    # Test architectural model
    print("\nTesting architectural model:")
    for entity in test_entities:
        print(f"\nChecking {entity}:")
        print(list_object_types_for_ifc_entity(model="arc", entity_type=entity))
    
    # Test MEP model
    print("\nTesting MEP model:")
    for entity in test_entities:
        print(f"\nChecking {entity}:")
        print(list_object_types_for_ifc_entity(model="mep", entity_type=entity))
    
    # Test with invalid entity type
    print("\nTesting with invalid entity type:")
    print(list_object_types_for_ifc_entity(model="arc", entity_type="InvalidType")) 