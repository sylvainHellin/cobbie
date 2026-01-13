import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Callable, Union


def get_element_distribution_by_type_object(
    model: ifcopenshell.file,
    element_type: str,
    group_by_type_attribute: str = 'Name',
    include_element_details: bool = False,
    element_attributes: List[str] = ['Name', 'GlobalId'],
    include_percentages: bool = True,
    sort_by: Optional[str] = 'count',
    sort_order: str = 'desc',
    empty_label: str = 'No Type',
    filter_func: Optional[Callable[[Any], bool]] = None,
    pset_name: Optional[str] = None,
    property_name: Optional[str] = None,
    property_value: Any = None
) -> Dict[str, Dict[str, Any]]:
    """
    Groups elements of a specified IFC type by their associated TypeObject,
    with optional filtering by element properties or custom function.

    This function resolves the relationship between typed elements (e.g., IfcFurnishingElement)
    and their TypeObject definitions (e.g., IfcFurnitureType) to enable quantitative
    analysis based on formal type classifications. Elements can be filtered before
    grouping using a custom function or by matching specific property values.

    Args:
        model: The loaded IFC model instance
        element_type: The IFC element class to query (e.g., 'IfcFurnishingElement', 'IfcDoor', 'IfcWindow')
        group_by_type_attribute: Attribute of the TypeObject to group by (default: 'Name').
            Can be 'Name', 'GlobalId', 'ObjectType', or other TypeObject attributes.
        include_element_details: If True, includes lists of elements for each type group (default: False)
        element_attributes: Which element attributes to include when include_element_details=True
            (default: ['Name', 'GlobalId'])
        include_percentages: Whether to calculate percentage of total for each group (default: True)
        sort_by: Sort results by 'count', 'name', or None for unsorted (default: 'count')
        sort_order: 'asc' or 'desc' (default: 'desc')
        empty_label: Label for elements with no associated TypeObject (default: 'No Type')
        filter_func: Optional callable that takes an element and returns True to include it.
            If provided, only elements passing this filter are counted.
        pset_name: Optional Property Set name to filter by (e.g., 'ArchiCADProperties').
            If provided along with property_name and property_value, filters elements
            where this property equals property_value.
        property_name: Optional Property name within the pset_name to filter by (e.g., 'Ebene').
        property_value: Value to match for the property. Comparison is strict equality.

    Returns:
        A dictionary where keys are the values from the TypeObject attribute, and each value contains:
            - 'count': Number of elements in this group
            - 'percentage': Percentage of total (only if include_percentages=True)
            - 'type_id': GlobalId of the TypeObject (or 'Unknown' if no type)
            - 'elements': List of element details (only if include_element_details=True)

        Returns empty dict {} if no elements of the specified type are found or if all are filtered out.

    Example:
        >>> # Standard usage
        >>> result = get_element_distribution_by_type_object(model, 'IfcWallStandardCase')

        >>> # Filtered usage: Count exterior walls only
        >>> result = get_element_distribution_by_type_object(
        ...     model, 'IfcWallStandardCase',
        ...     pset_name='ArchiCADProperties',
        ...     property_name='Ebene',
        ...     property_value='Außenwände'
        ... )
    """
    # Get all elements of the specified type
    elements = model.by_type(element_type)

    # Handle empty input
    if not elements:
        return {}

    # Validate sort_order
    if sort_order not in ('asc', 'desc'):
        sort_order = 'desc'

    # Dictionary to store grouped results
    groups: Dict[str, Dict[str, Any]] = {}

    skipped_count = 0
    filtered_count = 0
    total_count = 0

    for elem in elements:
        try:
            # --- Filtering Logic ---
            include_element = True

            # 1. Property-based filtering
            if pset_name and property_name:
                prop_match_found = False

                # Iterate through IsDefinedBy relationships to find the property
                for definition in elem.IsDefinedBy:
                    if hasattr(definition, 'RelatingPropertyDefinition'):
                        prop_def = definition.RelatingPropertyDefinition

                        # Check PSet name
                        if hasattr(prop_def, 'Name') and prop_def.Name == pset_name:
                            if hasattr(prop_def, 'HasProperties'):
                                for prop in prop_def.HasProperties:
                                    # Check Property name
                                    if prop.Name == property_name:
                                        # Get value, handling IfcValue wrapper (NominalValue)
                                        nominal = getattr(prop, 'NominalValue', None)
                                        actual_value = None
                                        if nominal:
                                            actual_value = getattr(nominal, 'wrappedValue', nominal)

                                        # Compare values
                                        if actual_value == property_value:
                                            prop_match_found = True
                                        break
                        if prop_match_found:
                            break

                if not prop_match_found:
                    include_element = False
                    filtered_count += 1

            # 2. Custom function filtering
            if include_element and filter_func:
                try:
                    if not filter_func(elem):
                        include_element = False
                        filtered_count += 1
                except Exception:
                    # If filter function fails, exclude element to be safe
                    include_element = False
                    filtered_count += 1

            if not include_element:
                continue

            # --- Grouping Logic ---
            # Get the type object associated with this element
            type_obj = ifcopenshell.util.element.get_type(elem)

            if type_obj is not None:
                # Get the grouping key from the TypeObject attribute
                group_key = getattr(type_obj, group_by_type_attribute, None)
                type_id = getattr(type_obj, 'GlobalId', 'Unknown')

                if group_key is None:
                    group_key = empty_label
                    type_id = 'Unknown'
            else:
                # No type object associated
                group_key = empty_label
                type_id = 'Unknown'

            # Initialize group if not exists
            if group_key not in groups:
                groups[group_key] = {
                    'count': 0,
                    'type_id': type_id,
                    'elements': []
                }

            # Increment count
            groups[group_key]['count'] += 1
            total_count += 1

            # Add element details if requested
            if include_element_details:
                element_details = {}
                for attr in element_attributes:
                    element_details[attr] = getattr(elem, attr, '')
                groups[group_key]['elements'].append(element_details)

        except AttributeError:
            skipped_count += 1
            continue
        except RuntimeError:
            skipped_count += 1
            continue

    # Calculate percentages if requested
    if include_percentages and total_count > 0:
        for group_data in groups.values():
            group_data['percentage'] = round(
                (group_data['count'] / total_count) * 100, 1
            )

    # Remove 'elements' key if not requested
    if not include_element_details:
        for group_data in groups.values():
            if 'elements' in group_data:
                del group_data['elements']

    # Sort results if requested
    if sort_by == 'count':
        reverse = sort_order == 'desc'
        groups = dict(
            sorted(groups.items(), key=lambda x: x[1]['count'], reverse=reverse)
        )
    elif sort_by == 'name':
        reverse = sort_order == 'desc'
        groups = dict(
            sorted(groups.items(), key=lambda x: str(x[0]), reverse=reverse)
        )

    # Report status
    if skipped_count > 0:
        print(f"Warning: Skipped {skipped_count} elements due to errors")

    return groups