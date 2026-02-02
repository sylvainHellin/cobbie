import ifcopenshell
from typing import Dict, List, Optional, Tuple, Any


def calculate_total_quantity(
    model: ifcopenshell.file,
    element_type: str,
    quantity_name: str,
    predefined_type: Optional[str] = None,
    include_details: bool = False
) -> Dict[str, Any]:
    """
    Calculates the total value of a specific quantity across filtered IFC elements.

    This function navigates the IsDefinedBy relationships to find IfcElementQuantity sets,
    locates quantities by name, and extracts values from type-specific attributes.
    It supports different quantity types (IfcQuantityVolume, IfcQuantityArea, IfcQuantityLength,
    IfcQuantityCount, IfcQuantityWeight, IfcQuantityTime).

    Args:
        model: The IFC model instance (ifcopenshell.file)
        element_type: IFC entity type to analyze (e.g., 'IfcSlab', 'IfcWall', 'IfcBeam')
        quantity_name: Name of the quantity to extract (e.g., 'NetVolume', 'GrossArea', 'Length')
        predefined_type: Optional filter by PredefinedType attribute (e.g., 'FLOOR', 'USERDEFINED')
        include_details: If True, returns per-element values in the result

    Returns:
        Dict containing:
            - 'total': The aggregated sum of all found quantity values (float)
            - 'count': Number of elements where the quantity was found (int)
            - 'elements': Optional list of (element_name, value) tuples if include_details=True
            - 'total_elements': Total number of elements matching the type filter (int)

    Example usage:
        >>> model = ifcopenshell.open('model.ifc')
        >>> result = calculate_total_quantity(
        ...     model,
        ...     element_type='IfcSlab',
        ...     quantity_name='NetVolume',
        ...     predefined_type='FLOOR'
        ... )
        >>> print(f"Total volume: {result['total']} m³")
    """
    # Get all elements of the specified type
    elements = model.by_type(element_type)
    
    if not elements:
        return {
            'total': 0.0,
            'count': 0,
            'total_elements': 0,
            'elements': [] if include_details else None
        }
    
    # Filter by PredefinedType if specified
    if predefined_type is not None:
        filtered_elements = []
        for elem in elements:
            elem_type = getattr(elem, 'PredefinedType', None)
            if elem_type == predefined_type:
                filtered_elements.append(elem)
        elements = filtered_elements
    
    total_elements_count = len(elements)
    
    # Map quantity types to their value attributes
    quantity_attr_map = {
        'IfcQuantityVolume': 'VolumeValue',
        'IfcQuantityArea': 'AreaValue',
        'IfcQuantityLength': 'LengthValue',
        'IfcQuantityCount': 'CountValue',
        'IfcQuantityWeight': 'WeightValue',
        'IfcQuantityTime': 'TimeValue'
    }
    
    total = 0.0
    count = 0
    element_details = [] if include_details else None
    skipped = 0
    
    for elem in elements:
        value = None
        
        try:
            # Navigate IsDefinedBy relationships to find IfcElementQuantity
            for rel in elem.IsDefinedBy:
                if not hasattr(rel, 'RelatingPropertyDefinition'):
                    continue
                    
                pdef = rel.RelatingPropertyDefinition
                if not pdef.is_a('IfcElementQuantity'):
                    continue
                
                # Search for the specific quantity by name
                for quant in pdef.Quantities:
                    if quant.Name == quantity_name:
                        quant_type = quant.is_a()
                        attr_name = quantity_attr_map.get(quant_type)
                        
                        if attr_name and hasattr(quant, attr_name):
                            value = getattr(quant, attr_name)
                            break
            
            if value is not None:
                total += value
                count += 1
                
                if include_details:
                    elem_name = getattr(elem, 'Name', 'Unnamed')
                    element_details.append((elem_name, value))
                    
        except (AttributeError, TypeError):
            # Skip elements with unexpected structure
            skipped += 1
            continue
    
    if skipped > 0:
        print(f"Warning: Skipped {skipped} elements due to unexpected structure")
    
    return {
        'total': total,
        'count': count,
        'total_elements': total_elements_count,
        'elements': element_details
    }