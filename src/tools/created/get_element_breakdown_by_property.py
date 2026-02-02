import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Any, Optional, Union

def get_element_breakdown_by_property(
    model,
    element_type: str,
    group_by_pset: str,
    group_by_property: str,
    value_pset: str,
    value_property: str,
    name_attribute: str = 'Name',
    sort_groups: bool = True,
    include_individual_values: bool = True,
    aggregate_values: bool = True,
    value_label: str = 'Value'
) -> Dict[str, Dict[str, Any]]:
    """
    Gets a breakdown of elements grouped by one property, with values extracted from another property.
    Useful for queries like 'Space breakdown by level with individual room areas', 
    'Wall breakdown by fire rating with lengths', or 'Door breakdown by type with heights'.

    Args:
        model: The IFC model instance.
        element_type: IFC entity type to analyze (e.g., 'IfcSpace', 'IfcWall').
        group_by_pset: Property set name for grouping (e.g., 'Constraints', 'Pset_WallCommon').
        group_by_property: Property name for grouping (e.g., 'Level', 'FireRating').
        value_pset: Property set name for value extraction (e.g., 'Dimensions', 'Qto_WallBaseQuantities').
        value_property: Property name for value extraction (e.g., 'Area', 'Length').
        name_attribute: Attribute to use as element name (default: 'Name').
        sort_groups: If True, sorts groups alphabetically (default: True).
        include_individual_values: If True, includes individual element values (default: True).
        aggregate_values: If True, calculates total and average per group (default: True).
        value_label: Label for the extracted value in output (default: 'Value').

    Returns:
        Dict mapping group names to breakdown info:
        {
            'Group Name': {
                'count': int,
                'total': float (if aggregate_values=True),
                'average': float (if aggregate_values=True),
                'elements': [
                    {'name': str, value_label: float},
                    ...
                ] (if include_individual_values=True)
            },
            ...
        }
    """
    # Get all elements of the specified type
    elements = model.by_type(element_type)
    
    if not elements:
        return {}

    # Dictionary to store grouped results
    grouped_data: Dict[str, Dict[str, Any]] = {}
    skipped_count = 0

    for element in elements:
        try:
            # Get element name
            elem_name = getattr(element, name_attribute, None)
            if elem_name is None:
                elem_name = getattr(element, 'LongName', 'Unknown')
            elif not isinstance(elem_name, str):
                elem_name = str(elem_name)

            # Get grouping key
            group_key = ifcopenshell.util.element.get_pset(
                element, group_by_pset, group_by_property
            )

            if group_key is None:
                group_key = "Undefined"
            elif not isinstance(group_key, str):
                group_key = str(group_key)

            # Get value
            value = ifcopenshell.util.element.get_pset(
                element, value_pset, value_property
            )
            
            # Try to convert value to float for aggregation
            numeric_value: Optional[float] = None
            if value is not None:
                try:
                    numeric_value = float(value)
                except (ValueError, TypeError):
                    pass # Keep as is if not numeric, but don't aggregate

            # Initialize group entry if not exists
            if group_key not in grouped_data:
                entry: Dict[str, Any] = {
                    'count': 0,
                    'elements': []
                }
                if aggregate_values:
                    entry['total'] = 0.0
                    entry['average'] = 0.0
                    entry['valid_values_count'] = 0
                grouped_data[group_key] = entry

            # Update group data
            grouped_data[group_key]['count'] += 1
            
            # Prepare element info dict
            element_info: Dict[str, Any] = {'name': elem_name}
            element_info[value_label] = value # Store original value
            
            if include_individual_values:
                grouped_data[group_key]['elements'].append(element_info)
            
            if aggregate_values and numeric_value is not None:
                grouped_data[group_key]['total'] += numeric_value
                grouped_data[group_key]['valid_values_count'] += 1
                
        except Exception:
            # Log and skip elements that cause errors
            skipped_count += 1
            continue

    # Post-processing: Calculate averages
    if aggregate_values:
        for group_key, data in grouped_data.items():
            valid_count = data.get('valid_values_count', 0)
            if valid_count > 0:
                data['average'] = data['total'] / valid_count
            else:
                data['average'] = 0.0
            # Remove internal counter from output
            if 'valid_values_count' in data:
                del data['valid_values_count']

    # Sort groups if requested
    if sort_groups:
        return dict(sorted(grouped_data.items()))

    return grouped_data