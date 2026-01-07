import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Union, Callable

def get_property_values_for_elements(
    model: ifcopenshell.file,
    ifc_class: str,
    pset_name: str,
    prop_name: str,
    element_identifier: str = 'Name',
    include_null: bool = False,
    value_filter: Optional[Union[Any, Callable[[Any], bool]]] = None
) -> List[Dict[str, Any]]:
    """
    Retrieves specific property values for elements of a given IFC class, mapping 
    element identifiers to their values, with optional filtering.

    This function iterates through elements of the specified class, locates the defined 
    property set (or quantity set) and property, and extracts the value. It handles 
    different attribute types for the element name and supports unwrapping IFC quantity 
    objects (e.g., IfcQuantityLength) to their primitive values.

    Args:
        model (ifcopenshell.file): The opened IFC model.
        ifc_class (str): The IFC class to query (e.g., 'IfcSpace', 'IfcWall').
        pset_name (str): The name of the Property Set containing the target property 
            (e.g., 'Qto_SpaceBaseQuantities', 'Pset_WallCommon').
        prop_name (str): The name of the property to retrieve (e.g., 'Height', 'IsExternal').
        element_identifier (str): The attribute to use as the key/label for the element 
            (e.g., 'Name', 'LongName', 'GlobalId'). Defaults to 'Name'.
        include_null (bool): If True, includes elements where the property is missing 
            with a None value. Defaults to False.
        value_filter (Optional[Union[Any, Callable[[Any], bool]]]): A value or function to filter results.
            - If a simple value (int, str, bool, etc.), returns only elements where the 
              property value equals this filter.
            - If a callable, it is called with the property value; returns only elements 
              where it returns True.
            - If None (default), no filtering is applied.

    Returns:
        List[Dict[str, Any]]: A list of dictionaries, where each dictionary contains 
            the element's identifier and the property value. 
            (e.g., [{'Name': 'Room 1', 'Value': 3.5}, ...]).

    Example Usage:
        >>> model = ifcopenshell.open('path/to/model.ifc')
        >>> # Get all heights
        >>> heights = get_property_values_for_elements(
        ...     model, 'IfcSpace', 'Qto_SpaceBaseQuantities', 'Height'
        ... )
        >>> # Get only exterior walls
        >>> exterior_walls = get_property_values_for_elements(
        ...     model, 'IfcWall', 'Pset_WallCommon', 'IsExternal', value_filter=True
        ... )
    """
    results: List[Dict[str, Any]] = []
    elements = model.by_type(ifc_class)

    for element in elements:
        # Get all property sets for the element
        try:
            psets = ifcopenshell.util.element.get_psets(element)
        except Exception:
            psets = {}

        value = None
        if pset_name in psets:
            props = psets[pset_name]
            if prop_name in props:
                raw_value = props[prop_name]
                
                # Handle IFC Quantity objects (e.g., IfcQuantityLength) which wrap the value
                if hasattr(raw_value, 'length_value'):
                    value = raw_value.length_value
                elif hasattr(raw_value, 'area_value'):
                    value = raw_value.area_value
                elif hasattr(raw_value, 'volume_value'):
                    value = raw_value.volume_value
                elif hasattr(raw_value, 'weight_value'):
                    value = raw_value.weight_value
                elif hasattr(raw_value, 'time_value'):
                    value = raw_value.time_value
                else:
                    # It's likely a primitive or simple wrapper
                    value = raw_value

        # Check inclusion criteria based on Nulls
        if value is None and not include_null:
            continue

        # Check inclusion criteria based on Filter
        if value_filter is not None:
            try:
                if callable(value_filter):
                    # If it's a callable, use the result of the function
                    if not value_filter(value):
                        continue
                else:
                    # If it's a value, perform equality check
                    if value != value_filter:
                        continue
            except Exception:
                # If filter logic fails (e.g. type mismatch), skip element
                continue

        # Get the identifier attribute value safely
        id_value = None
        try:
            id_value = getattr(element, element_identifier, None)
            if id_value and hasattr(id_value, 'wrappedValue'):
                id_value = id_value.wrappedValue
        except Exception:
            pass

        # Construct the result dictionary
        result_item: Dict[str, Any] = {}
        result_item[element_identifier] = id_value
        result_item['Value'] = value
        
        results.append(result_item)

    return results