import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Any, Optional, Callable

def get_element_distribution_by_attribute(
    model: ifcopenshell.file,
    ifc_type: str,
    group_by_attribute: str = 'Name',
    include_percentages: bool = True,
    sort_by: str = 'count',
    sort_order: str = 'desc',
    empty_label: str = '(Empty)',
    include_elements: bool = False,
    element_attributes: Optional[List[str]] = None,
    value_parser: Optional[Callable[[str], str]] = None,
    filter_pset_name: Optional[str] = None,
    filter_prop_name: Optional[str] = None,
    filter_prop_value: Any = None
) -> Dict[str, Dict[str, Any]]:
    """
    Groups elements of a specified IFC type by a given attribute (e.g., Name, ObjectType)
    and returns the count and percentage of each group. This handles the common BIM analysis
    question 'What types of elements exist in the model and how many of each?' when elements
    are classified by attributes rather than formal TypeObjects.

    Args:
        model: The loaded IFC model instance.
        ifc_type: The IFC class name(s) to analyze (e.g., 'IfcBeam', 'IfcWindow').
        group_by_attribute: The attribute to group elements by (default: 'Name').
        include_percentages: Whether to calculate percentages (default: True).
        sort_by: Sort results by 'count' or 'attribute value' (default: 'count').
        sort_order: 'desc' or 'asc' (default: 'desc').
        empty_label: Label for None/empty values (default: '(Empty)').
        include_elements: If True, includes an 'elements' list in the result for each group (default: False).
        element_attributes: Optional list of specific attributes to extract for each element.
                          If None and include_elements is True, raw entity instances are returned.
        value_parser: Optional callable function to transform attribute values before grouping.
                      Accepts the raw string value and returns the cleaned string for grouping.
                      Useful for stripping IDs or normalizing naming conventions.
        filter_pset_name: The name of the PropertySet to check (e.g., 'Pset_WallCommon').
                         If provided along with filter_prop_name and filter_prop_value,
                         only elements matching this property value will be included.
        filter_prop_name: The name of the Property within the set to evaluate (e.g., 'IsExternal').
        filter_prop_value: The value to match against (e.g., False).

    Returns:
        Dict mapping attribute values to dicts containing 'count', optionally 'percentage', and 'elements'.
        Example: {
            "BeamTypeA": {"count": 10, "percentage": 50.0, "elements": [...]},
            "BeamTypeB": {"count": 10, "percentage": 50.0, "elements": [...]}
        }

    Example Usage:
        >>> model = ifcopenshell.open('model.ifc')
        >>> # Summary only (backward compatible)
        >>> distribution = get_element_distribution_by_attribute(
        ...     model,
        ...     'IfcBeam',
        ...     group_by_attribute='Name'
        ... )
        >>> # Filter by property value (e.g., load-bearing walls only)
        >>> load_bearing_walls = get_element_distribution_by_attribute(
        ...     model,
        ...     'IfcWall',
        ...     group_by_attribute='ObjectType',
        ...     filter_pset_name='Pset_WallCommon',
        ...     filter_prop_name='LoadBearing',
        ...     filter_prop_value=True
        ... )
    """
    # Input validation
    if model is None:
        raise ValueError("Model cannot be None")

    if not ifc_type:
        raise ValueError("ifc_type must be specified")

    allowed_sort_by = ['count', 'attribute value']
    if sort_by not in allowed_sort_by:
        raise ValueError(f"sort_by must be one of {allowed_sort_by}")

    allowed_sort_order = ['desc', 'asc']
    if sort_order not in allowed_sort_order:
        raise ValueError(f"sort_order must be one of {allowed_sort_order}")

    # Determine if filtering is active (all three params must be provided)
    filter_active = (
        filter_pset_name is not None and
        filter_prop_name is not None and
        filter_prop_value is not None
    )

    # Retrieve elements of the specified type
    elements = model.by_type(ifc_type)

    if not elements:
        return {}

    distribution: Dict[str, Dict[str, Any]] = {}
    skipped_attr = 0
    filter_skipped = 0
    filter_error = 0
    
    filtered_elements = []

    # 1. Filter elements if filtering is active
    for element in elements:
        if filter_active:
            matches_filter = False
            try:
                # Use ifcopenshell.util.element.get_psets for robust access
                # We expect the exact value unwrapped
                prop_val = ifcopenshell.util.element.get_pset(
                    element, 
                    filter_pset_name, 
                    filter_prop_name
                )
                
                # Direct comparison
                if prop_val == filter_prop_value:
                    matches_filter = True
                    
            except (AttributeError, KeyError, RuntimeError):
                # Property or Pset not found, or access error
                filter_error += 1
            except Exception:
                # Catch other unexpected errors related to property access
                filter_error += 1

            if matches_filter:
                filtered_elements.append(element)
            else:
                filter_skipped += 1
        else:
            # No filter, include all elements
            filtered_elements.append(element)

    if not filtered_elements:
        return {}

    # 2. Group elements by attribute
    for element in filtered_elements:
        try:
            # Access attribute safely
            raw_value = getattr(element, group_by_attribute)

            # Handle None or empty strings
            if raw_value is None or (isinstance(raw_value, str) and raw_value.strip() == ''):
                key = empty_label
            else:
                key = str(raw_value)

            # Apply value parser if provided
            if value_parser is not None:
                try:
                    parsed_value = value_parser(key)
                    if parsed_value is None or (isinstance(parsed_value, str) and parsed_value.strip() == ''):
                        key = empty_label
                    else:
                        key = str(parsed_value)
                except Exception:
                    skipped_attr += 1
                    continue

        except AttributeError:
            skipped_attr += 1
            continue
        except Exception:
            skipped_attr += 1
            continue

        # Initialize group entry if needed
        if key not in distribution:
            distribution[key] = {'count': 0}
            if include_elements:
                distribution[key]['elements'] = []
            if include_percentages:
                distribution[key]['percentage'] = 0.0

        distribution[key]['count'] += 1

        # Handle element inclusion if requested
        if include_elements:
            if element_attributes:
                elem_data = {}
                for attr in element_attributes:
                    try:
                        elem_data[attr] = getattr(element, attr)
                    except AttributeError:
                        elem_data[attr] = None
                distribution[key]['elements'].append(elem_data)
            else:
                distribution[key]['elements'].append(element)

    # Calculate percentages based on the count of valid filtered elements processed
    if include_percentages:
        total_valid = len(filtered_elements) - skipped_attr
        if total_valid > 0:
            for key in distribution:
                count = distribution[key]['count']
                distribution[key]['percentage'] = round((count / total_valid) * 100, 2)

    # Sort results
    reverse_sort = (sort_order == 'desc')

    def get_sort_key(item: tuple):
        key, data = item
        if sort_by == 'count':
            return data['count']
        elif sort_by == 'attribute value':
            return key.lower() if isinstance(key, str) else key
        return 0

    sorted_distribution = dict(
        sorted(distribution.items(), key=get_sort_key, reverse=reverse_sort)
    )

    # Report skipped elements if any
    if filter_active and filter_skipped > 0:
        print(f"Info: {filter_skipped} elements filtered out (did not match property criteria).")
        if filter_error > 0:
            print(f"Info: {filter_error} elements skipped due to property access errors.")
    
    if skipped_attr > 0:
        print(f"Warning: Skipped {skipped_attr} elements due to missing attribute '{group_by_attribute}' or parsing errors.")

    return sorted_distribution