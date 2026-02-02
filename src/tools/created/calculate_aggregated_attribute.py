import ifcopenshell
from typing import Literal, Optional, Dict, Any

def calculate_aggregated_attribute(
    model: ifcopenshell.file,
    entity_type: str,
    attribute_name: str,
    aggregation: Literal['sum', 'avg', 'min', 'max', 'count'] = 'avg',
    include_details: bool = False,
    default_value: Optional[float] = None
) -> Dict[str, Any]:
    """
    Calculates aggregated values of entity attributes for all elements of a given IFC type.
    
    This function handles direct entity attributes (like OverallWidth for IfcDoor, 
    OverallHeight for IfcWindow) rather than Property Set properties.

    Args:
        model: The IFC model instance
        entity_type: IFC entity type to analyze (e.g., 'IfcDoor', 'IfcWindow', 'IfcSlab')
        attribute_name: Name of the entity attribute to aggregate 
                       (e.g., 'OverallWidth', 'OverallHeight', 'Thickness')
        aggregation: Type of aggregation to perform. Options: 'sum', 'avg', 'min', 'max', 'count'
        include_details: If True, returns individual element values along with aggregate
        default_value: Value to use if attribute is None/missing. 
                      If None, elements with missing attributes are skipped.

    Returns:
        Dictionary containing:
        - 'value': The aggregated result (float for sum/avg/min/max, int for count)
        - 'count': Number of elements with valid data used in aggregation
        - 'total_elements': Total number of elements of the entity type found
        - 'skipped': Number of elements skipped (missing attribute or None)
        - 'details': Optional list of dicts with 'id', 'name', 'value' for each element
                    (only if include_details=True)

    Raises:
        ValueError: If aggregation type is invalid or no valid data is found
        RuntimeError: If the entity_type does not exist in the IFC schema

    Example usage:
        >>> model = ifcopenshell.open('path/to/model.ifc')
        >>> result = calculate_aggregated_attribute(
        ...     model, 'IfcDoor', 'OverallWidth', 'avg'
        ... )
        >>> print(f"Average door width: {result['value']:.3f} m")
    """
    # Validate aggregation type
    valid_aggregations = ['sum', 'avg', 'min', 'max', 'count']
    if aggregation not in valid_aggregations:
        raise ValueError(f"Invalid aggregation '{aggregation}'. Must be one of: {valid_aggregations}")
    
    # Get all elements of the specified type
    try:
        elements = model.by_type(entity_type)
    except RuntimeError as e:
        raise RuntimeError(f"Entity type '{entity_type}' not found in IFC schema") from e
    
    total_elements = len(elements)
    
    if total_elements == 0:
        raise ValueError(f"No elements found for entity type '{entity_type}'")
    
    values = []
    details = []
    skipped = 0
    
    for element in elements:
        try:
            # Get the attribute value - use getattr for safe access
            attr_value = getattr(element, attribute_name, None)
            
            # Handle None/missing attributes
            if attr_value is None:
                if default_value is not None:
                    attr_value = default_value
                else:
                    skipped += 1
                    continue
            
            # Ensure the value is numeric
            try:
                numeric_value = float(attr_value)
            except (ValueError, TypeError):
                skipped += 1
                continue
            
            values.append(numeric_value)
            
            if include_details:
                details.append({
                    'id': element.id(),
                    'name': element.Name,
                    'value': numeric_value
                })
                
        except AttributeError:
            skipped += 1
            continue
    
    # Check if we have valid data
    if len(values) == 0:
        raise ValueError(
            f"No valid '{attribute_name}' attribute data found for {entity_type}. "
            f"Checked {total_elements} elements, {skipped} skipped."
        )
    
    # Calculate the aggregation
    count = len(values)
    
    if aggregation == 'sum':
        result_value = sum(values)
    elif aggregation == 'avg':
        result_value = sum(values) / count
    elif aggregation == 'min':
        result_value = min(values)
    elif aggregation == 'max':
        result_value = max(values)
    elif aggregation == 'count':
        result_value = count
    
    # Build return dictionary
    return_dict = {
        'value': result_value,
        'count': count,
        'total_elements': total_elements,
        'skipped': skipped
    }
    
    if include_details:
        return_dict['details'] = details
    
    return return_dict