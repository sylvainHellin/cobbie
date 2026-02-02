import ifcopenshell
import ifcopenshell.util.element
from typing import List, Callable, Any, Optional

def filter_elements_by_pset_property(
    elements: Optional[List[ifcopenshell.entity_instance]] = None,
    pset_name: Optional[str] = None,
    property_name: Optional[str] = None,
    property_value: Any = None,
    comparator: Optional[Callable[[Any], bool]] = None,
    model: Optional[Any] = None,
    entity_type: Optional[str] = None
) -> List[ifcopenshell.entity_instance]:
    """
    Filters a list of IFC elements based on the value of a specific property within a Property Set (Pset).

    This function abstracts the logic of navigating property definitions to check property values.
    It leverages ifcopenshell.util.element.get_pset to handle standard types and inheritance.

    Args:
        elements (Optional[List[ifcopenshell.entity_instance]]): The list of IFC elements to filter
            (e.g., model.by_type('IfcWall')). If None, `model` and `entity_type` must be provided.
        pset_name (Optional[str]): The name of the Property Set to search within (e.g., 'Pset_WallCommon').
        property_name (Optional[str]): The name of the property to evaluate (e.g., 'IsExternal').
        property_value (Any, optional): The value to match against the property's value.
            If None and no comparator is provided, the function checks for the existence of the property.
        comparator (Callable, optional): A function that takes the found property value and returns a boolean.
            Useful for complex checks (e.g., lambda x: x is True). If provided, overrides property_value matching.
        model (Optional[Any]): The IFC model instance (from ifcopenshell.open()). Required if `elements` is None.
        entity_type (Optional[str]): The IFC entity type string (e.g., 'IfcDoor'). Required if `elements` is None.

    Returns:
        List[ifcopenshell.entity_instance]: A filtered list containing only elements that match the criteria.
            Returns an empty list if input is invalid or no matches found.

    Raises:
        ValueError: If neither `elements` nor both `model` and `entity_type` are provided.

    Example:
        >>> # Usage Pattern 1: Traditional with pre-fetched elements
        >>> walls = model.by_type('IfcWall')
        >>> exterior_walls = filter_elements_by_pset_property(
        ...     walls, 'Pset_WallCommon', 'IsExternal', True
        ... )
        >>> print(f"Found {len(exterior_walls)} exterior walls.")
        
        >>> # Usage Pattern 2: Self-contained with model and entity_type
        >>> interior_doors = filter_elements_by_pset_property(
        ...     pset_name='Pset_DoorCommon',
        ...     property_name='IsExternal',
        ...     property_value=False,
        ...     model=model,
        ...     entity_type='IfcDoor'
        ... )
        >>> print(f"Found {len(interior_doors)} interior doors.")
    """
    # Resolve elements list based on provided arguments
    elements_to_filter = None
    
    if elements is not None:
        # Traditional usage: use provided elements list
        elements_to_filter = elements
    elif model is not None and entity_type is not None:
        # Self-contained usage: fetch elements from model
        try:
            elements_to_filter = model.by_type(entity_type)
        except RuntimeError:
            # Invalid entity type or schema issue - treat as empty result
            return []
    else:
        # Invalid usage: neither elements nor (model + entity_type) provided
        raise ValueError(
            "Either 'elements' list must be provided, or both 'model' and 'entity_type' must be provided."
        )
    
    # Validate that we have elements to process
    if not elements_to_filter:
        return []
    
    filtered_elements = []
    skipped_count = 0

    for element in elements_to_filter:
        try:
            # Use the utility function to get the specific property value
            # This handles inheritance from types and raw IFC value extraction (like IfcBoolean)
            value = ifcopenshell.util.element.get_pset(element, pset_name, property_name)

            # If the property doesn't exist on this element (and not inherited), skip
            if value is None:
                # If the user was just checking for existence (property_value is None and no comparator),
                # we treat None as "not found", so we skip.
                if property_value is None and comparator is None:
                    continue
                # If checking for a specific value, None won't match, so skip implicitly
                continue

            # Determine if the element matches the criteria
            is_match = False
            if comparator:
                # Use custom logic provided by the user
                try:
                    is_match = comparator(value)
                except Exception:
                    # If comparator fails, we treat it as non-matching to avoid crashing the loop
                    is_match = False
            elif property_value is not None:
                # Direct value comparison
                is_match = (value == property_value)
            else:
                # No property_value and no comparator provided implies "check existence"
                # Since we reached here, value is not None, so it exists.
                is_match = True

            if is_match:
                filtered_elements.append(element)

        except (AttributeError, KeyError, RuntimeError):
            # Handle cases where the element structure is unexpected or retrieval fails
            skipped_count += 1
            continue

    if skipped_count > 0:
        print(f"Warning: Skipped {skipped_count} elements due to errors during property retrieval.")

    return filtered_elements