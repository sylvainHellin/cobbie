import ifcopenshell
import ifcopenshell.util.element
from typing import Any, Dict, List, Optional, Union, Callable, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    import ifcopenshell

def get_element_distribution_by_property(
    model: 'ifcopenshell.file',
    ifc_type: Union[str, List[str]],
    pset_name: str,
    prop_name: str,
    include_percentages: bool = True,
    sort_by: Optional[Literal['count', 'value']] = 'count',
    sort_order: Literal['asc', 'desc'] = 'desc',
    empty_label: Optional[str] = 'Not Defined',
    value_parser: Optional[Callable[[Any], Any]] = None,
    return_elements: bool = False,
    element_attributes: List[str] = ['Name', 'GlobalId'],
    filter_func: Optional[Callable] = None,
    aggregate_quantity_name: Optional[str] = None,
    quantity_set_name: Optional[str] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Groups elements of a specified IFC type by a property value and returns the count, 
    percentage of each unique value, and optionally the sum of a specified quantity.

    This function addresses common BIM analysis questions like 'How many walls are load-bearing 
    vs non-load-bearing?' or 'What is the total floor area per building level?'

    Args:
        model: The loaded IFC model instance
        ifc_type: The IFC class name(s) to analyze (e.g., 'IfcWall' or ['IfcWall', 'IfcCurtainWall'])
        pset_name: The property set name (e.g., 'Pset_WallCommon', 'Constraints')
        prop_name: The property name to group by (e.g., 'LoadBearing', 'Level')
        include_percentages: Whether to include percentage calculations (default: True)
        sort_by: How to sort the groups - 'count' or 'value' (default: 'count')
        sort_order: Sort order - 'asc' or 'desc' (default: 'desc')
        empty_label: Label for elements missing the property, or None to exclude (default: 'Not Defined')
        value_parser: Optional function to transform values before grouping
        return_elements: Whether to include element details in each group (default: False)
        element_attributes: Attributes to include for each element (default: ['Name', 'GlobalId'])
        filter_func: Optional function to filter elements before grouping
        aggregate_quantity_name: Optional name of the quantity to sum per group (e.g., 'NetFloorArea')
        quantity_set_name: Optional name of the QuantitySet containing the quantity. If None, searches all.

    Returns:
        A dictionary mapping property values to distribution data:
        {
            'value1': {'count': 10, 'percentage': 20.0, 'total_quantity_value': 150.5, 'elements': [...]},
            'value2': {'count': 40, 'percentage': 80.0, 'total_quantity_value': 600.0, 'elements': [...]},
            '_meta': {'total': 50, 'missing': 0, 'has_property': 50, 'skipped': 0}
        }

    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> distribution = get_element_distribution_by_property(
        ...     model,
        ...     ifc_type='IfcSpace',
        ...     pset_name='Constraints',
        ...     prop_name='Level',
        ...     aggregate_quantity_name='NetFloorArea'
        ... )
        >>> print(distribution['Groundfloor']['total_quantity_value'])
        229.95
    """
    
    # Internal helper to get quantity value robustly
    def _get_quantity_value(element: 'ifcopenshell.entity_instance', q_name: str, qset_filter: Optional[str]) -> float:
        try:
            for rel in element.IsDefinedBy:
                if not hasattr(rel, 'RelatingPropertyDefinition'):
                    continue
                
                pdef = rel.RelatingPropertyDefinition
                
                # We only care about IfcElementQuantity (has Quantities attribute)
                if not hasattr(pdef, 'Quantities'):
                    continue
                    
                # Filter by QuantitySet name if provided
                if qset_filter is not None and pdef.Name != qset_filter:
                    continue
                
                for q in pdef.Quantities:
                    if q.Name == q_name:
                        # Handle various quantity types found in IFC
                        if hasattr(q, 'AreaValue'):
                            return float(q.AreaValue)
                        elif hasattr(q, 'VolumeValue'):
                            return float(q.VolumeValue)
                        elif hasattr(q, 'LengthValue'):
                            return float(q.LengthValue)
                        elif hasattr(q, 'CountValue'):
                            return float(q.CountValue)
                        elif hasattr(q, 'WeightValue'):
                            return float(q.WeightValue)
                        elif hasattr(q, 'TimeValue'):
                            return float(q.TimeValue)
        except (AttributeError, RuntimeError):
            # Element structure might be unexpected
            pass
        return 0.0

    # Normalize ifc_type to list
    if isinstance(ifc_type, str):
        ifc_types = [ifc_type]
    else:
        ifc_types = ifc_type
    
    # Collect all elements of specified types
    elements: List['ifcopenshell.entity_instance'] = []
    for itype in ifc_types:
        try:
            elements.extend(model.by_type(itype))
        except RuntimeError:
            # Invalid IFC type - continue with other types
            continue
    
    # Apply filter function if provided
    if filter_func is not None:
        try:
            elements = [e for e in elements if filter_func(e)]
        except Exception:
            # Filter function failed - continue with all elements
            pass
    
    # Validate input
    if not elements:
        return {'_meta': {'total': 0, 'missing': 0, 'has_property': 0, 'skipped': 0}}
    
    # Initialize counters
    total = len(elements)
    missing_count = 0
    has_property_count = 0
    skipped_count = 0
    
    # Group elements by property value
    groups: Dict[str, List['ifcopenshell.entity_instance']] = {}
    
    for element in elements:
        try:
            # Get the property set using utility function
            psets = ifcopenshell.util.element.get_psets(element, psets_only=True)
            
            if pset_name not in psets:
                # Property set not found
                if empty_label is not None:
                    key = str(empty_label)
                    if key not in groups:
                        groups[key] = []
                    groups[key].append(element)
                missing_count += 1
                continue
            
            # Get the property value
            pset = psets[pset_name]
            
            if prop_name not in pset:
                # Property not found in the property set
                if empty_label is not None:
                    key = str(empty_label)
                    if key not in groups:
                        groups[key] = []
                    groups[key].append(element)
                missing_count += 1
                continue
            
            value = pset[prop_name]
            
            # Apply value parser if provided
            if value_parser is not None:
                try:
                    value = value_parser(value)
                except Exception:
                    # Parser failed, use original value
                    pass
            
            # Convert to string for dictionary key
            key = str(value)
            
            if key not in groups:
                groups[key] = []
            groups[key].append(element)
            has_property_count += 1
            
        except (AttributeError, KeyError, RuntimeError):
            # Element processing failed - skip this element
            skipped_count += 1
            continue
    
    # Calculate total for percentage calculation
    processed_total = total - skipped_count
    if processed_total == 0:
        return {'_meta': {'total': 0, 'missing': 0, 'has_property': 0, 'skipped': skipped_count}}
    
    # Build result dictionary
    result: Dict[str, Dict[str, Any]] = {}
    
    for key, element_list in groups.items():
        count = len(element_list)
        group_data: Dict[str, Any] = {'count': count}
        
        if include_percentages:
            percentage = (count / processed_total) * 100 if processed_total > 0 else 0
            group_data['percentage'] = round(percentage, 2)
        
        # Calculate quantity aggregation if requested
        if aggregate_quantity_name:
            total_quantity = 0.0
            for elem in element_list:
                try:
                    total_quantity += _get_quantity_value(elem, aggregate_quantity_name, quantity_set_name)
                except Exception:
                    pass
            group_data['total_quantity_value'] = round(total_quantity, 2)
        else:
            group_data['total_quantity_value'] = 0.0
        
        if return_elements:
            group_data['elements'] = []
            for elem in element_list:
                elem_data: Dict[str, Any] = {}
                for attr in element_attributes:
                    try:
                        elem_data[attr] = getattr(elem, attr, None)
                    except AttributeError:
                        elem_data[attr] = None
                group_data['elements'].append(elem_data)
        
        result[key] = group_data
    
    # Sort the groups (excluding _meta)
    sorted_keys = [k for k in result.keys() if k != '_meta']
    
    if sort_by == 'count':
        sorted_keys.sort(key=lambda k: result[k]['count'], reverse=(sort_order == 'desc'))
    elif sort_by == 'value':
        sorted_keys.sort(reverse=(sort_order == 'desc'))
    
    # Create new dictionary with sorted order
    sorted_result: Dict[str, Dict[str, Any]] = {}
    for key in sorted_keys:
        sorted_result[key] = result[key]
    
    # Add _meta information
    sorted_result['_meta'] = {
        'total': processed_total,
        'missing': missing_count,
        'has_property': has_property_count,
        'skipped': skipped_count
    }
    
    return sorted_result