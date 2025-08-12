import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.util.placement
import ifcopenshell.util.geolocation
import ifcopenshell.util.system
import ifcopenshell.geom
import math
import json
from typing import List

def get_entity_names(model_path: str, entity_type: str) -> List[str]:
    """
    Retrieve the names of all entities of a specified type from an IFC model.
    
    Args:
        model_path (str): The file path to the IFC model.
        entity_type (str): The IFC entity type to query (e.g., 'IfcSpace').
        
    Returns:
        List[str]: A list of names of the entities.
    """
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Retrieve all entities of the specified type
    entities = model.by_type(entity_type)
    
    # Extract the Name attribute from each entity, filtering out entities without a name
    names = []
    for entity in entities:
        # Check if the entity has a Name attribute and it's not None
        if hasattr(entity, 'Name') and entity.Name is not None:
            names.append(entity.Name)
    
    return names