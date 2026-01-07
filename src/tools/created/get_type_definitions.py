import ifcopenshell
from typing import List, Dict, Any, Optional

def get_type_definitions(model: ifcopenshell.file, ifc_class: str, name_filter: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Finds type definitions for a given IFC element class, automatically handling 
    schema differences between IFC2X3 (e.g., IfcWindowStyle, IfcDoorStyle) and IFC4+ 
    (e.g., IfcWindowType, IfcDoorType). This function searches for type entities directly, 
    even when no instances of the element class exist in the model.

    Args:
        model (ifcopenshell.file): The opened IFC model.
        ifc_class (str): The IFC element class to find types for 
            (e.g., 'IfcWindow', 'IfcWall', 'IfcDoor').
        name_filter (Optional[str]): Optional case-insensitive substring to filter type names. 
            Defaults to None.

    Returns:
        List[Dict[str, Any]]: List of type definitions with keys: 
            'id' (int), 'type_entity' (str), 'name' (str), 'properties' (Dict).

    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> walls = get_type_definitions(model, 'IfcWall')
        >>> for wall in walls:
        ...     print(f"{wall['name']}: {wall['properties']}")
    """
    results: List[Dict[str, Any]] = []
    
    # 1. Identify potential entity names for the type definition.
    # Priority 1: Standard IFC4+ naming (e.g., IfcWindowType)
    standard_type_name = f"{ifc_class}Type"
    
    # Priority 2: IFC2X3 specific 'Style' naming for certain elements
    # In IFC2X3, Windows, Doors, CurtainWalls, Members, and Plates use Styles instead of Types.
    ifc2x3_style_mapping: Dict[str, str] = {
        "IfcWindow": "IfcWindowStyle",
        "IfcDoor": "IfcDoorStyle",
        "IfcCurtainWall": "IfcCurtainWallStyle",
        "IfcMember": "IfcMemberStyle",
        "IfcPlate": "IfcPlateStyle"
    }
    
    style_type_name = ifc2x3_style_mapping.get(ifc_class)
    
    # 2. Attempt to retrieve entities from the model
    entities = []
    
    # Try Standard Type first (works for IFC4 and IFC2X3 for non-styled elements like walls)
    try:
        entities = model.by_type(standard_type_name)
    except RuntimeError:
        # If standard type doesn't exist in schema (e.g. IfcWindowType in IFC2X3), 
        # try Style if a mapping exists
        if style_type_name:
            try:
                entities = model.by_type(style_type_name)
            except RuntimeError:
                # Entity does not exist in this schema, return empty
                pass

    # 3. Process found entities
    for entity in entities:
        entity_name = entity.Name if entity.Name else "Unnamed"
        
        # Apply name filter if provided
        if name_filter and name_filter.lower() not in entity_name.lower():
            continue
            
        # Extract Properties
        properties: Dict[str, Any] = {}
        
        # Robust check for HasPropertySets attribute and value
        if hasattr(entity, 'HasPropertySets') and entity.HasPropertySets:
            for pset in entity.HasPropertySets:
                # Safely get Pset Name
                pset_name = pset.Name if hasattr(pset, 'Name') and pset.Name else pset.is_a()
                
                if hasattr(pset, 'HasProperties') and pset.HasProperties:
                    pset_props: Dict[str, Any] = {}
                    for prop in pset.HasProperties:
                        prop_name = prop.Name if hasattr(prop, 'Name') and prop.Name else "Unknown"
                        
                        # Extract value safely, handling the wrapper structure of NominalValue
                        val = None
                        if hasattr(prop, 'NominalValue'):
                            # In Python-ifcopenshell, values are often wrapped
                            if hasattr(prop.NominalValue, 'wrappedValue'):
                                val = prop.NominalValue.wrappedValue
                            else:
                                val = prop.NominalValue
                        
                        pset_props[prop_name] = val
                    
                    properties[pset_name] = pset_props

        results.append({
            'id': entity.id(),
            'type_entity': entity.is_a(),
            'name': entity_name,
            'properties': properties
        })
        
    return results