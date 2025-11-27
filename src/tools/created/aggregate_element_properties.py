import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Union, Optional, Any

def aggregate_element_properties(
    ifc_file: ifcopenshell.file,
    element_type: str,
    property_set_name: str,
    property_name: str,
    aggregation_type: str = 'sum',
    group_by_property: Optional[Dict[str, str]] = None,
    include_details: bool = False
) -> Dict[str, Any]:
    """
    Aggregates property values from IFC elements of a specified type, supporting sum, average, 
    count, min, and max operations. This function handles the common pattern of extracting 
    quantitative data from element properties and performing statistical analysis. It can 
    optionally group results by another property (like level) for detailed breakdowns.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type string (e.g., 'IfcSpace', 'IfcWall')
        property_set_name: Name of property set containing the target property 
                          (e.g., 'PSet_Revit_Dimensions')
        property_name: Name of property to aggregate (e.g., 'Area', 'Length', 'Width')
        aggregation_type: Type of aggregation ('sum', 'average', 'count', 'min', 'max')
        group_by_property: Optional dict {'property_set': str, 'property_name': str} to 
                         group results (e.g., {'property_set': 'PSet_Revit_Constraints', 
                         'property_name': 'Level'})
        include_details: Boolean to include individual element values in results.
    
    Returns:
        Dict containing aggregated value(s), element count, and optional grouping breakdown.
        Structure:
        {
            'aggregated_value': Union[float, int],
            'element_count': int,
            'aggregation_type': str,
            'group_breakdown': Optional[Dict[str, Dict[str, Any]]],  # if group_by_property provided
            'element_details': Optional[List[Dict[str, Any]]]  # if include_details=True
        }
    
    Example:
        >>> ifc_file = ifcopenshell.open('model.ifc')
        >>> result = aggregate_element_properties(
        ...     ifc_file, 'IfcSpace', 'PSet_Revit_Dimensions', 'Area', 'sum'
        ... )
        >>> print(result['aggregated_value'])  # Total area of all spaces
    """
    
    # Validate aggregation type
    valid_aggregations = ['sum', 'average', 'count', 'min', 'max']
    if aggregation_type not in valid_aggregations:
        raise ValueError(f"Invalid aggregation_type '{aggregation_type}'. Must be one of: {valid_aggregations}")
    
    # Get all elements of the specified type
    try:
        elements = ifc_file.by_type(element_type)
    except Exception as e:
        raise ValueError(f"Error getting elements of type '{element_type}': {e}")
    
    if not elements:
        return {
            'aggregated_value': 0 if aggregation_type in ['sum', 'count'] else None,
            'element_count': 0,
            'aggregation_type': aggregation_type,
            'group_breakdown': {} if group_by_property else None,
            'element_details': [] if include_details else None
        }
    
    # Collect property values from all elements
    values = []
    element_details = []
    grouped_values = {} if group_by_property else None
    
    for element in elements:
        element_name = getattr(element, 'Name', None) or getattr(element, 'LongName', None) or f"Element_{element.id()}"
        
        # Get the target property value
        try:
            property_value = ifcopenshell.util.element.get_pset(element, property_set_name, property_name)
        except:
            property_value = None
        
        # Get grouping property if specified
        group_value = None
        if group_by_property:
            try:
                group_value = ifcopenshell.util.element.get_pset(
                    element, 
                    group_by_property['property_set'], 
                    group_by_property['property_name']
                )
            except:
                group_value = 'Unknown'
        
        # Only process elements that have the target property (except for count)
        if aggregation_type != 'count' and property_value is None:
            continue
        
        # Convert to appropriate type for numeric operations
        if aggregation_type != 'count' and property_value is not None:
            try:
                numeric_value = float(property_value)
                values.append(numeric_value)
            except (ValueError, TypeError):
                continue  # Skip non-numeric values
        
        # Store element details if requested
        if include_details:
            detail = {
                'element_id': element.id(),
                'element_name': element_name,
                'property_value': property_value if aggregation_type != 'count' else 1
            }
            if group_by_property:
                detail['group_value'] = group_value
            element_details.append(detail)
        
        # Group values if grouping is specified
        if group_by_property and group_value is not None:
            if group_value not in grouped_values:
                grouped_values[group_value] = []
            
            if aggregation_type != 'count' and property_value is not None:
                try:
                    grouped_values[group_value].append(float(property_value))
                except (ValueError, TypeError):
                    pass
            elif aggregation_type == 'count':
                grouped_values[group_value].append(1)  # Count as 1
    
    # Calculate aggregated value
    aggregated_value = None
    if aggregation_type == 'count':
        aggregated_value = len(values) if values else len(elements)
    elif values:
        if aggregation_type == 'sum':
            aggregated_value = sum(values)
        elif aggregation_type == 'average':
            aggregated_value = sum(values) / len(values)
        elif aggregation_type == 'min':
            aggregated_value = min(values)
        elif aggregation_type == 'max':
            aggregated_value = max(values)
    
    # Calculate group breakdowns
    group_breakdown = None
    if group_by_property and grouped_values:
        group_breakdown = {}
        for group_name, group_vals in grouped_values.items():
            if not group_vals:
                continue
                
            group_result = {
                'count': len(group_vals),
                'sum': sum(group_vals),
                'average': sum(group_vals) / len(group_vals),
                'min': min(group_vals),
                'max': max(group_vals)
            }
            group_breakdown[group_name] = group_result
    
    return {
        'aggregated_value': aggregated_value,
        'element_count': len(values) if aggregation_type != 'count' else (len(values) if values else len(elements)),
        'aggregation_type': aggregation_type,
        'group_breakdown': group_breakdown,
        'element_details': element_details if include_details else None
    }