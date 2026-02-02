import ifcopenshell
from typing import Dict, Any, Optional

def get_element_classification_breakdown(
    model: ifcopenshell.file,
    entity_type: str,
    check_predefined_type: bool = True,
    check_type_objects: bool = True,
    type_object_attribute: str = 'Name',
    pset_name: Optional[str] = None,
    pset_property_name: Optional[str] = None,
    return_simple_counts_by_type_object: bool = False
) -> Dict[str, Any]:
    """
    Analyzes elements of a specific IFC type to determine their classification
    based on PredefinedType attribute, IsTypedBy relationship (Type Objects),
    and optionally Property Set values.

    Args:
        model: The IFC model instance.
        entity_type: The IFC entity type to analyze (e.g., 'IfcRailing', 'IfcWindow').
        check_predefined_type: If True, analyzes the 'PredefinedType' attribute of elements.
        check_type_objects: If True, analyzes the 'IsTypedBy' relationship to find Type Objects.
        type_object_attribute: The attribute of the Type Object to extract (e.g., 'Name', 'GlobalId').
        pset_name: If specified, classifies elements by values in this property set.
        pset_property_name: If specified along with pset_name, classifies by this specific property value.
                           If None and pset_name is specified, uses all properties as the classification key.
        return_simple_counts_by_type_object: If True, adds a 'simple_type_counts' key with a flat
                                            dictionary of {type_object_attribute_value: count}.
                                            This provides the same output as get_element_counts_by_type_object.

    Returns:
        A dictionary containing:
            - 'total_count': Total number of elements found.
            - 'predefined_types' (optional): Dict of unique PredefinedType values and their counts.
            - 'type_objects' (optional): Dict of unique Type Object attribute values and their counts.
            - 'simple_type_counts' (optional): Flat dict of type object counts when return_simple_counts_by_type_object=True.
            - 'pset_classification' (optional): Dict of unique property set values and their counts.
            - 'skipped_count': Number of elements skipped due to errors during processing.

    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> # Original usage (backward compatible)
        >>> result = get_element_classification_breakdown(model, 'IfcRailing')
        >>> # New usage with simple type counts
        >>> result = get_element_classification_breakdown(model, 'IfcFurniture',
        ...                                              return_simple_counts_by_type_object=True)
        >>> print(result['simple_type_counts'])
        {'Chair Type A': 10, 'Desk Type B': 5}
        >>> # New usage with property set classification
        >>> result = get_element_classification_breakdown(model, 'IfcPipeSegment',
        ...                                              pset_name='Pset_ManufacturerTypeInformation',
        ...                                              pset_property_name='ModelReference')
        >>> print(result['pset_classification'])
        {'HT sewer pipe DN 100': 64, 'Copper pipes length 5 m 15x1 mm': 514}
    """
    # Initialize result dictionary
    result: Dict[str, Any] = {
        'total_count': 0,
        'skipped_count': 0
    }
    
    if check_predefined_type:
        result['predefined_types'] = {}
    if check_type_objects:
        result['type_objects'] = {}
    if pset_name is not None:
        result['pset_classification'] = {}
    if return_simple_counts_by_type_object:
        result['simple_type_counts'] = {}
    
    # Get all elements of the specified type
    elements = model.by_type(entity_type)
    result['total_count'] = len(elements)
    
    if not elements:
        return result
    
    # Process each element
    for element in elements:
        # Check PredefinedType if requested
        if check_predefined_type:
            try:
                if hasattr(element, 'PredefinedType'):
                    ptype = element.PredefinedType
                    # Handle None or null values
                    if ptype is None:
                        ptype = 'Undefined'
                    result['predefined_types'][ptype] = result['predefined_types'].get(ptype, 0) + 1
                else:
                    # Element doesn't have PredefinedType attribute (e.g. IFC2x3)
                    result['predefined_types']['Attribute Not Available'] = result['predefined_types'].get('Attribute Not Available', 0) + 1
            except RuntimeError:
                # Handle rare runtime errors during attribute access
                result['skipped_count'] += 1
        
        # Check Type Objects if requested (or if simple counts requested)
        if check_type_objects or return_simple_counts_by_type_object:
            try:
                # IsTypedBy is an inverse attribute, available on IfcObject definitions
                if hasattr(element, 'IsTypedBy') and element.IsTypedBy:
                    # IsTypedBy is a list of IfcRelDefinesByType (usually just one)
                    rel = element.IsTypedBy[0]
                    
                    if hasattr(rel, 'RelatingType') and rel.RelatingType:
                        type_obj = rel.RelatingType
                        
                        # Get the requested attribute from the Type Object
                        if hasattr(type_obj, type_object_attribute):
                            attr_value = getattr(type_obj, type_object_attribute)
                            if attr_value is None:
                                attr_value = 'Undefined'
                        else:
                            attr_value = f'Attribute {type_object_attribute} Not Available'
                        
                        # Update type_objects if check_type_objects is True
                        if check_type_objects:
                            result['type_objects'][attr_value] = result['type_objects'].get(attr_value, 0) + 1
                        
                        # Update simple_type_counts if return_simple_counts_by_type_object is True
                        if return_simple_counts_by_type_object:
                            result['simple_type_counts'][attr_value] = result['simple_type_counts'].get(attr_value, 0) + 1
                    else:
                        if check_type_objects:
                            result['type_objects']['No RelatingType'] = result['type_objects'].get('No RelatingType', 0) + 1
                        if return_simple_counts_by_type_object:
                            result['simple_type_counts']['No RelatingType'] = result['simple_type_counts'].get('No RelatingType', 0) + 1
                else:
                    # IsTypedBy is empty or not applicable
                    if check_type_objects:
                        result['type_objects']['Not Typed'] = result['type_objects'].get('Not Typed', 0) + 1
                    if return_simple_counts_by_type_object:
                        result['simple_type_counts']['Not Typed'] = result['simple_type_counts'].get('Not Typed', 0) + 1
            except (AttributeError, IndexError, RuntimeError):
                # Catch specific errors during relationship traversal
                result['skipped_count'] += 1
        
        # Check Property Set if requested
        if pset_name is not None:
            try:
                psets = ifcopenshell.util.element.get_psets(element, psets_only=True)
                
                if pset_name in psets:
                    pset_data = psets[pset_name]
                    
                    if pset_property_name is not None:
                        # Classify by a specific property
                        if pset_property_name in pset_data:
                            prop_value = pset_data[pset_property_name]
                            if prop_value is None:
                                prop_value = 'Undefined'
                        else:
                            prop_value = f'Property {pset_property_name} Not Found'
                        classification_key = str(prop_value)
                    else:
                        # Classify by all properties in the pset (create a composite key)
                        # Exclude 'id' from the key as it's an internal identifier
                        prop_items = [(k, v) for k, v in pset_data.items() if k != 'id']
                        if prop_items:
                            # Sort by property name for consistent keys
                            prop_items.sort(key=lambda x: x[0])
                            classification_key = ', '.join([f'{k}={v}' for k, v in prop_items])
                        else:
                            classification_key = 'Empty Property Set'
                    
                    result['pset_classification'][classification_key] = result['pset_classification'].get(classification_key, 0) + 1
                else:
                    result['pset_classification']['Pset Not Found'] = result['pset_classification'].get('Pset Not Found', 0) + 1
            except (AttributeError, KeyError, RuntimeError):
                result['skipped_count'] += 1
    
    return result