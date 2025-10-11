import ifcopenshell
from typing import List, Union, Optional

def get_entity_names(model_path: str, entity_type: Union[str, List[str]]) -> List[str]:
    """
    Retrieve the names of all entities of specified type(s) from an IFC model.
    
    This function retrieves all entities of the specified type(s) and extracts their names.
    It can handle single entity types or multiple related entity types to ensure
    comprehensive coverage of the model data. This is particularly useful for
    entities that have multiple related types (e.g., IfcWall and IfcWallStandardCase).
    
    Args:
        model_path (str): The file path to the IFC model.
        entity_type (Union[str, List[str]]): The IFC entity type to query. Can be a single
            type (e.g., 'IfcSpace', 'IfcBuildingStorey') or a list of related types
            (e.g., ['IfcWall', 'IfcWallStandardCase']) for comprehensive analysis.
        
    Returns:
        List[str]: A list of names of the entities. Includes None values converted to
                  'None' for debugging purposes, and empty strings as-is. When multiple
                  entity types are provided, names from all types are combined.
                  
    Raises:
        FileNotFoundError: If the IFC model file does not exist.
        ValueError: If the IFC model cannot be opened, entity_type is invalid, or
                   no entities of the specified type(s) are found.
        
    Examples:
        # Single entity type
        wall_names = get_entity_names('model.ifc', 'IfcWall')
        
        # Multiple related types for comprehensive analysis
        all_wall_names = get_entity_names('model.ifc', ['IfcWall', 'IfcWallStandardCase'])
        
    Note:
        This function is designed to be inclusive rather than exclusive in entity retrieval
        to avoid missing entities due to type filtering issues. All entities of the specified
        type(s) are returned, with their names preserved or marked as None.
        
        For comprehensive analysis of entity families (like walls), it's recommended
        to provide all related entity types as a list to ensure complete coverage.
        
        The function validates entity types and will raise a ValueError for invalid types
        rather than returning error messages as results.
    """
    import os
    
    # Check if file exists
    if not os.path.exists(model_path):
        raise FileNotFoundError(f"IFC model file not found at '{model_path}'")
    
    try:
        # Load the IFC model
        model = ifcopenshell.open(model_path)
    except Exception as e:
        raise ValueError(f"Failed to open IFC model at '{model_path}': {e}")
    
    # Normalize entity_type to a list for uniform processing
    if isinstance(entity_type, str):
        entity_types = [entity_type]
    elif isinstance(entity_type, list):
        entity_types = entity_type
    else:
        raise ValueError(f"entity_type must be a string or list of strings, got {type(entity_type)}")
    
    # Validate entity types and collect names
    all_names = []
    found_entities = False
    
    for etype in entity_types:
        if not isinstance(etype, str) or not etype.strip():
            raise ValueError(f"Invalid entity type: {etype}. Must be a non-empty string.")
        
        try:
            # Retrieve all entities of the specified type
            entities = model.by_type(etype)
            
            if not entities:
                # If no entities found for this type, continue to next type
                # Don't raise error here as other types in the list might have entities
                continue
                
            found_entities = True
            
            # Extract the Name attribute from each entity
            for entity in entities:
                # Get the name attribute, handle various cases
                if hasattr(entity, 'Name'):
                    if entity.Name is None:
                        all_names.append("None")  # Convert None to string for debugging
                    elif entity.Name == "":
                        all_names.append("")  # Keep empty string as-is
                    else:
                        all_names.append(str(entity.Name))  # Ensure it's a string
                else:
                    all_names.append("No_Name_Attribute")  # Mark entities without Name attribute
                    
        except RuntimeError as e:
            # Handle invalid entity type errors from ifcopenshell
            if "not found in schema" in str(e):
                raise ValueError(f"Invalid IFC entity type: '{etype}'. This type does not exist in the IFC schema.")
            else:
                raise ValueError(f"Error retrieving entities of type '{etype}': {e}")
        except Exception as e:
            raise ValueError(f"Unexpected error retrieving entities of type '{etype}': {e}")
    
    # If no entities were found for any of the specified types, raise an informative error
    if not found_entities:
        type_str = "', '".join(entity_types) if len(entity_types) > 1 else entity_types[0]
        raise ValueError(f"No entities found of type(s): '{type_str}'. Please verify the entity type(s) exist in the model.")
    
    return all_names