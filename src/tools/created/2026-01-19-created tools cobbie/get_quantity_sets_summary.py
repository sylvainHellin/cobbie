import ifcopenshell
from typing import List, Dict, Union, Callable, Optional, Any


def get_quantity_sets_summary(
    model: ifcopenshell.file,
    ifc_type: Union[str, List[str]],
    filter_func: Optional[Callable[[ifcopenshell.entity_instance], bool]] = None,
    include_sample_elements: bool = False,
    max_samples: int = 3
) -> Dict[str, Any]:
    """
    Discovers and summarizes IfcElementQuantity sets defined on elements of specified IFC type(s).

    This function analyzes the quantity relationships (IfcElementQuantity) across elements,
    collects all unique quantity names found, and reports how many elements have quantity sets defined.
    This is useful for understanding what dimensional data (Length, Area, Volume, etc.) is available
    in the model before attempting to extract it.

    Args:
        model: The loaded IFC model instance
        ifc_type: The IFC class name(s) to query (e.g., 'IfcWall', ['IfcWall', 'IfcSlab'])
        filter_func: Optional function to filter elements before analysis.
                    Function should accept an element and return True to include it.
        include_sample_elements: If True, returns sample element details with their quantities
        max_samples: Maximum number of sample elements to return (default: 3)

    Returns:
        Dict with structure:
        {
            'total_elements': int,
            'elements_with_quantities': int,
            'elements_without_quantities': int,
            'coverage_percentage': float,
            'all_quantity_names': List[str],
            'quantity_sets_found': List[str],
            'sample_elements': Optional[List[Dict]]  # if include_sample_elements=True
        }

    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> summary = get_quantity_sets_summary(model, 'IfcWall')
        >>> print(f"Coverage: {summary['coverage_percentage']}%")
        >>> print(f"Quantities found: {summary['all_quantity_names']}")
    """
    # Normalize ifc_type to list
    if isinstance(ifc_type, str):
        ifc_types = [ifc_type]
    else:
        ifc_types = ifc_type

    # Collect all elements of specified types
    all_elements: List[ifcopenshell.entity_instance] = []
    for elem_type in ifc_types:
        try:
            elements = model.by_type(elem_type)
            all_elements.extend(elements)
        except RuntimeError:
            # Invalid IFC type - skip silently or could log warning
            continue

    # Apply filter function if provided
    if filter_func is not None:
        filtered_elements = [elem for elem in all_elements if filter_func(elem)]
    else:
        filtered_elements = all_elements

    total_elements = len(filtered_elements)

    # Early return if no elements found
    if total_elements == 0:
        return {
            'total_elements': 0,
            'elements_with_quantities': 0,
            'elements_without_quantities': 0,
            'coverage_percentage': 0.0,
            'all_quantity_names': [],
            'quantity_sets_found': [],
            'sample_elements': [] if include_sample_elements else None
        }

    # Track statistics and collected data
    elements_with_quantities = 0
    all_quantity_names = set()
    quantity_sets_found = set()
    sample_elements_data = []
    skipped_count = 0

    # Process each element
    for element in filtered_elements:
        try:
            has_quantities = False
            element_quantities = []

            # Check IsDefinedBy relationships for IfcElementQuantity
            if hasattr(element, 'IsDefinedBy'):
                for rel in element.IsDefinedBy:
                    try:
                        if hasattr(rel, 'RelatingPropertyDefinition'):
                            prop_def = rel.RelatingPropertyDefinition
                            if prop_def and hasattr(prop_def, 'is_a') and prop_def.is_a('IfcElementQuantity'):
                                has_quantities = True
                                
                                # Record the quantity set name
                                qset_name = getattr(prop_def, 'Name', 'Unnamed')
                                if qset_name:
                                    quantity_sets_found.add(qset_name)

                                # Collect quantity names from this set
                                if hasattr(prop_def, 'Quantities'):
                                    for q in prop_def.Quantities:
                                        q_name = getattr(q, 'Name', None)
                                        if q_name:
                                            all_quantity_names.add(q_name)
                                            # For sample elements, collect quantity details
                                            if include_sample_elements and len(sample_elements_data) < max_samples:
                                                q_value = getattr(q, 'LengthValue', None) or getattr(q, 'AreaValue', None) or getattr(q, 'VolumeValue', None)
                                                element_quantities.append({
                                                    'name': q_name,
                                                    'value': q_value
                                                })
                    except (AttributeError, TypeError):
                        skipped_count += 1
                        continue

            if has_quantities:
                elements_with_quantities += 1

            # Store sample element data if requested
            if include_sample_elements and has_quantities and len(sample_elements_data) < max_samples:
                sample_elements_data.append({
                    'element_id': element.id if hasattr(element, 'id') else None,
                    'element_name': getattr(element, 'Name', None),
                    'element_type': element.is_a() if hasattr(element, 'is_a') else None,
                    'global_id': getattr(element, 'GlobalId', None),
                    'quantities': element_quantities
                })

        except (AttributeError, TypeError):
            skipped_count += 1
            continue

    # Calculate coverage percentage
    coverage_percentage = (elements_with_quantities / total_elements * 100) if total_elements > 0 else 0.0

    result = {
        'total_elements': total_elements,
        'elements_with_quantities': elements_with_quantities,
        'elements_without_quantities': total_elements - elements_with_quantities,
        'coverage_percentage': round(coverage_percentage, 2),
        'all_quantity_names': sorted(list(all_quantity_names)),
        'quantity_sets_found': sorted(list(quantity_sets_found)),
        'sample_elements': sample_elements_data if include_sample_elements else None
    }

    return result