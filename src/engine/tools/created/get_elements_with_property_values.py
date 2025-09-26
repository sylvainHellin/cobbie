import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.util.placement
import ifcopenshell.util.geolocation
import ifcopenshell.util.system
import ifcopenshell.geom
import math
import json
from typing import List, Dict, Any, Optional

def get_elements_with_property_values(
    model_path: str,
    entity_type: str,
    property_names: List[str],
    name_pattern: Optional[str] = None,
    property_set_names: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Retrieves elements of a specified IFC type along with specific property values from their property sets.
    
    Args:
        model_path (str): Path to the IFC model file
        entity_type (str): IFC entity type to search for (e.g., "IfcWall", "IfcSlab")
        property_names (List[str]): List of property names to extract (e.g., ["FireRating", "Width", "LoadCapacity"])
        name_pattern (str, optional): Pattern to filter elements by name (case-insensitive substring match)
        property_set_names (List[str], optional): Specific property set names to search in (if None, search all common property sets)
        
    Returns:
        List[Dict[str, Any]]: List of dictionaries containing element information and requested property values
        
    Note:
        This function works with common property sets including PSet_* and Revit-specific sets.
        For Revit models, it will access properties from sets like PSet_Revit_Dimensions, PSet_Revit_Structural, etc.
    """
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Get all elements of the specified type
    elements = model.by_type(entity_type)
    
    # Filter elements by name pattern if provided
    if name_pattern:
        name_pattern_lower = name_pattern.lower()
        elements = [e for e in elements if e.Name and name_pattern_lower in e.Name.lower()]
    
    results = []
    
    # Process each element
    for element in elements:
        # Get all property sets for this element
        all_psets = ifcopenshell.util.element.get_psets(element)
        
        # Filter property sets if specific ones are requested
        if property_set_names:
            psets = {name: all_psets.get(name, {}) for name in property_set_names}
        else:
            psets = all_psets
        
        # Extract requested properties
        properties = {}
        for prop_name in property_names:
            # Look for the property in all available property sets
            prop_value = None
            for pset_name, pset_dict in psets.items():
                if prop_name in pset_dict:
                    prop_value = pset_dict[prop_name]
                    break
            properties[prop_name] = prop_value
        
        # Get container information
        container = ifcopenshell.util.element.get_container(element)
        container_name = container.Name if container and container.Name else None
        container_type = container.is_a() if container else None
        
        # Create result entry
        result_entry = {
            "element_name": element.Name if element.Name else "Unnamed",
            "element_guid": element.GlobalId,
            "element_type": element.is_a(),
            "properties": properties,
            "container_name": container_name,
            "container_type": container_type
        }
        
        results.append(result_entry)
    
    return results