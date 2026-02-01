import ifcopenshell
from typing import Dict, Any, Optional

def get_all_element_properties(
    model: ifcopenshell.file,
    element: ifcopenshell.entity_instance,
    include_type_properties: bool = True,
    filter_placeholders: bool = True,
    exclude_internal_ids: bool = True
) -> Dict[str, Any]:
    """
    Retrieves all property values for a specific IFC element instance, optionally including 
    properties from its associated Type Object.

    This function traverses the `IsDefinedBy` relationships and `HasPropertySets` attributes 
    to collect properties, merges instance and type-level data, and cleans common 
    placeholder values. It is designed for exploratory analysis to understand what 
    data defines a specific element.

    Args:
        model (ifcopenshell.file): The loaded IFC model.
        element (ifcopenshell.entity_instance): The specific element to query.
        include_type_properties (bool): If True (default), also extracts properties from 
            the element's Type Object via `IfcRelDefinesByType` and `HasPropertySets`.
        filter_placeholders (bool): If True (default), removes properties where the 
            value string equals the property name string (common in Revit exports).
        exclude_internal_ids (bool): If True (default), excludes properties named 'id' 
            from the result.

    Returns:
        Dict[str, Any]: A dictionary where keys are in the format 'PSetName.PropertyName' 
            and values are the property values. Returns an empty dict if the element is 
            invalid or has no valid properties.

    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('building.ifc')
        >>> walls = model.by_type('IfcWallStandardCase')
        >>> if walls:
        ...     props = get_all_element_properties(model, walls[0])
        ...     print(props.get('PSet_WallCommon.LoadBearing'))
    """
    if not element:
        return {}

    properties: Dict[str, Any] = {}

    def _extract_props(entity: ifcopenshell.entity_instance) -> Dict[str, Any]:
        """Internal helper to extract properties from an entity (Instance or Type)."""
        extracted: Dict[str, Any] = {}
        
        # 1. Check IsDefinedBy (Relationships)
        # Use getattr to safely access the attribute, default to None if missing
        is_defined_by = getattr(entity, 'IsDefinedBy', None)
        
        if is_defined_by:
            try:
                # Iterate safely, handling potential non-list items if data is corrupt
                for rel in is_defined_by:
                    if rel and rel.is_a('IfcRelDefinesByProperties'):
                        pset_def = getattr(rel, 'RelatingPropertyDefinition', None)
                        if pset_def and pset_def.is_a('IfcPropertySet'):
                            _process_pset(pset_def, extracted)
            except TypeError:
                # IsDefinedBy was not iterable (e.g., None or single entity not in list)
                pass

        # 2. Check HasPropertySets (Direct attribute on Type Objects)
        has_psets = getattr(entity, 'HasPropertySets', None)
        if has_psets:
            try:
                for pset in has_psets:
                    if pset and pset.is_a('IfcPropertySet'):
                        _process_pset(pset, extracted)
            except TypeError:
                pass
                
        return extracted

    def _process_pset(pset: ifcopenshell.entity_instance, collected: Dict[str, Any]):
        """Process a single PropertySet and add valid properties to the dictionary."""
        # Handle cases where pset.Name might be empty or None
        pset_name = getattr(pset, 'Name', 'UnnamedPSet') or 'UnnamedPSet'
        has_props = getattr(pset, 'HasProperties', None)
        
        if has_props:
            for prop in has_props:
                if prop and prop.is_a('IfcPropertySingleValue'):
                    prop_name = getattr(prop, 'Name', None)
                    if prop_name is None:
                        continue

                    if exclude_internal_ids and prop_name.lower() == 'id':
                        continue
                    
                    nom_val = getattr(prop, 'NominalValue', None)
                    if nom_val is not None:
                        val = nom_val.wrappedValue
                        
                        if filter_placeholders:
                            # Filter if value string equals property name string (common Revit placeholder)
                            if isinstance(val, str) and val == prop_name:
                                continue
                            
                        key = f"{pset_name}.{prop_name}"
                        collected[key] = val

    # 1. Extract Instance Properties
    properties.update(_extract_props(element))

    # 2. Extract Type Properties if requested
    if include_type_properties:
        type_obj = None
        is_defined_by = getattr(element, 'IsDefinedBy', None)
        
        if is_defined_by:
            try:
                for rel in is_defined_by:
                    if rel and rel.is_a('IfcRelDefinesByType'):
                        type_obj = getattr(rel, 'RelatingType', None)
                        if type_obj:
                            break
            except TypeError:
                pass

        if type_obj:
            type_props = _extract_props(type_obj)
            properties.update(type_props)

    return properties