import ifcopenshell
from typing import Dict, List, Optional, Callable


def group_elements_by_attribute(
    model: ifcopenshell.file,
    entity_type: str,
    attribute_name: str,
    default_value: str = 'NOTDEFINED',
    pattern_func: Optional[Callable[[str], str]] = None,
    pattern_default: str = 'UNKNOWN'
) -> Dict[str, List[ifcopenshell.entity_instance]]:
    """
    Groups IFC elements based on the unique values of a specific entity attribute.

    This function retrieves all elements of a given IFC type and categorizes them
    based on the value of a specified attribute. It handles cases where attributes
    are missing or None by using a default value. When a pattern_func is provided,
    it combines the attribute value with a pattern extracted from the element's Name
    for more granular classification.

    Args:
        model (ifcopenshell.file): The IFC model instance.
        entity_type (str): The IFC entity class to retrieve (e.g., 'IfcWall', 'IfcSlab').
        attribute_name (str): The name of the entity attribute to group by 
            (e.g., 'PredefinedType', 'ObjectType').
        default_value (str, optional): The key to use for elements missing the attribute 
            or where the value is None. Defaults to 'NOTDEFINED'.
        pattern_func (Optional[Callable[[str], str]], optional): A function that takes
            an element's Name string and returns a pattern/substring for sub-grouping.
            When provided, keys are formatted as '{attribute_value}: {pattern_value}'.
            Defaults to None.
        pattern_default (str, optional): The fallback value when pattern_func returns
            None or an empty string. Defaults to 'UNKNOWN'.

    Returns:
        Dict[str, List[ifcopenshell.entity_instance]]: A dictionary mapping attribute 
            values (or combined values if pattern_func is used) to lists of element instances.

    Example:
        >>> # Basic usage - group by PredefinedType
        >>> slab_groups = group_elements_by_attribute(model, 'IfcSlab', 'PredefinedType')
        >>> floor_slabs = slab_groups.get('FLOOR', [])
        >>> 
        >>> # Advanced usage - combine PredefinedType with name pattern
        >>> import re
        >>> def extract_slab_type(name):
        ...     match = re.search(r'_AT_.+?:(\\d+)$', name)
        ...     return match.group(1) if match else None
        >>> detailed_groups = group_elements_by_attribute(
        ...     model, 'IfcSlab', 'PredefinedType', 
        ...     pattern_func=extract_slab_type
        ... )
    """
    # Retrieve elements of the specified type
    try:
        elements = model.by_type(entity_type)
    except RuntimeError:
        return {}

    # Return empty dict if no elements found
    if not elements:
        return {}

    grouped_data: Dict[str, List[ifcopenshell.entity_instance]] = {}

    for element in elements:
        # Safely access the attribute
        raw_value = getattr(element, attribute_name, None)

        if raw_value is None:
            attr_key = default_value
        else:
            # Convert to string to handle Enum types (common in IFC PredefinedType)
            attr_key = str(raw_value)

        # Apply pattern function if provided
        if pattern_func is not None:
            # Get the element's name for pattern extraction
            name = getattr(element, 'Name', '')
            if name is None:
                name = ''
            
            # Apply the pattern function with exception handling
            try:
                pattern_value = pattern_func(name)
            except (AttributeError, TypeError, ValueError):
                pattern_value = None
            
            # Use default if pattern function returns None or empty string
            if not pattern_value:
                pattern_value = pattern_default
            
            # Combine attribute value with pattern value
            key = f"{attr_key}: {pattern_value}"
        else:
            key = attr_key

        # Initialize list for this key if it doesn't exist
        if key not in grouped_data:
            grouped_data[key] = []

        grouped_data[key].append(element)

    return grouped_data
