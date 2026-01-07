import ifcopenshell
from typing import Optional, Union, List


def get_aggregated_quantity_by_type_name(
    model: ifcopenshell.file,
    ifc_class: str,
    quantity_name: str,
    type_object_name: str,
    aggregate_type: str = 'sum'
) -> Optional[Union[float, int]]:
    """
    Calculates a statistical aggregation of a specific quantity for elements 
    filtered by their Type Object name.

    This function filters elements by checking their Type Object relationship,
    extracts the specified quantity from each element's quantity sets, and
    performs the requested aggregation.

    Args:
        model: The opened IFC model object
        ifc_class: The IFC element class to analyze (e.g., 'IfcWall', 'IfcWindow', 'IfcDoor')
        quantity_name: The name of the quantity to aggregate (e.g., 'Length', 'Area', 'Volume', 'Height')
        type_object_name: The exact Name of the Type Object to filter by
                          (e.g., 'Basic Wall:STB 250', 'Window Type X')
        aggregate_type: Type of aggregation to perform. Options:
                        - 'sum': Sum of all quantity values (default)
                        - 'avg': Average (mean) of quantity values
                        - 'min': Minimum quantity value
                        - 'max': Maximum quantity value
                        - 'count': Count of elements with the specified quantity

    Returns:
        The aggregated value as float or int, or None if no matching elements
        or quantities are found.

    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('path/to/model.ifc')
        >>> # Get total length of exterior walls
        >>> total_length = get_aggregated_quantity_by_type_name(
        ...     model, 'IfcWall', 'Length', 'Basic Wall:STB 250', 'sum'
        ... )
        >>> print(f'Total length: {total_length} m')
        >>> # Get average area of specific window type
        >>> avg_area = get_aggregated_quantity_by_type_name(
        ...     model, 'IfcWindow', 'Area', 'Window Type A', 'avg'
        ... )
    """
    try:
        # Validate aggregate_type
        valid_aggregates = ['sum', 'avg', 'min', 'max', 'count']
        if aggregate_type not in valid_aggregates:
            raise ValueError(f"Invalid aggregate_type '{aggregate_type}'. Must be one of: {valid_aggregates}")

        # Get all elements of the specified class
        elements = model.by_type(ifc_class)
        if not elements:
            return None

        # Filter elements by type object name
        filtered_elements = []
        for element in elements:
            try:
                # Check IsTypedBy relationship to find the type object
                if element.IsTypedBy:
                    relating_type = element.IsTypedBy[0].RelatingType
                    if relating_type.Name == type_object_name:
                        filtered_elements.append(element)
            except (AttributeError, IndexError):
                # Element doesn't have the expected structure, skip it
                continue

        if not filtered_elements:
            return None

        # Extract quantity values from filtered elements
        quantity_values: List[float] = []
        for element in filtered_elements:
            try:
                # Traverse IsDefinedBy relationships to find quantities
                for definition in element.IsDefinedBy:
                    if hasattr(definition, 'RelatingPropertyDefinition'):
                        prop_def = definition.RelatingPropertyDefinition
                        if hasattr(prop_def, 'Quantities'):
                            for quantity in prop_def.Quantities:
                                if quantity.Name == quantity_name:
                                    # Get the quantity value - try common attribute names
                                    value = None
                                    if hasattr(quantity, 'LengthValue'):
                                        value = quantity.LengthValue
                                    elif hasattr(quantity, 'AreaValue'):
                                        value = quantity.AreaValue
                                    elif hasattr(quantity, 'VolumeValue'):
                                        value = quantity.VolumeValue
                                    elif hasattr(quantity, 'WidthValue'):
                                        value = quantity.WidthValue
                                    elif hasattr(quantity, 'HeightValue'):
                                        value = quantity.HeightValue
                                    
                                    if value is not None:
                                        quantity_values.append(float(value))
                                    break
            except (AttributeError, IndexError, TypeError):
                # Element doesn't have the expected quantity structure, skip it
                continue

        # If no quantities found
        if not quantity_values:
            # For 'count', return the number of filtered elements even without quantity values
            if aggregate_type == 'count':
                return len(filtered_elements)
            return None

        # Perform aggregation
        if aggregate_type == 'sum':
            return sum(quantity_values)
        elif aggregate_type == 'avg':
            return sum(quantity_values) / len(quantity_values)
        elif aggregate_type == 'min':
            return min(quantity_values)
        elif aggregate_type == 'max':
            return max(quantity_values)
        elif aggregate_type == 'count':
            return len(quantity_values)
        
    except Exception as e:
        # Return None on any unexpected error
        return None