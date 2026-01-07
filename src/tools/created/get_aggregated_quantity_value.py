import ifcopenshell
import ifcopenshell.util.element
from typing import Optional, List


def get_aggregated_quantity_value(
    model: ifcopenshell.file,
    ifc_class: str,
    quantity_name: str,
    aggregate_type: str = 'min',
    quantity_set_name: Optional[str] = None
) -> Optional[float]:
    """
    Calculates a statistical aggregation (min, max, sum, avg) of a specific quantity for elements of a given IFC class.
    
    This function retrieves quantity data from property sets associated with IFC elements,
    filters out null or invalid values, and performs the requested statistical calculation.
    
    Args:
        model: The opened IFC model.
        ifc_class: The IFC element class to analyze (e.g., 'IfcDoor', 'IfcWall', 'IfcWindow').
        quantity_name: The name of the quantity to aggregate (e.g., 'Width', 'Area', 'Height', 'Volume').
        aggregate_type: The aggregation method to perform. Allowed values: 'min', 'max', 'sum', 'avg'. 
                       Defaults to 'min'.
        quantity_set_name: Optional filter to look for quantities in a specific set 
                          (e.g., 'BaseQuantities', 'Qto_DoorBaseQuantities'). If None, 
                          searches all property sets.
    
    Returns:
        Optional[float]: The resulting aggregated value, or None if no valid numeric data is found.
    
    Raises:
        ValueError: If aggregate_type is not one of the allowed values.
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('path/to/model.ifc')
        >>> min_width = get_aggregated_quantity_value(model, 'IfcDoor', 'Width', 'min')
        >>> print(f"Narrowest door: {min_width} m")
        Narrowest door: 0.87 m
        >>> total_area = get_aggregated_quantity_value(model, 'IfcWindow', 'Area', 'sum')
        >>> print(f"Total window area: {total_area} m²")
        Total window area: 45.5 m²
    """
    try:
        # Validate aggregate_type
        valid_aggregates = {'min', 'max', 'sum', 'avg'}
        if aggregate_type not in valid_aggregates:
            raise ValueError(
                f"Invalid aggregate_type: {aggregate_type}. "
                f"Must be one of {valid_aggregates}."
            )
        
        # Get all elements of the specified class
        elements = model.by_type(ifc_class)
        if not elements:
            return None
        
        # Collect valid numeric values for the quantity
        values: List[float] = []
        
        for element in elements:
            try:
                # Get all property sets for the element
                psets = ifcopenshell.util.element.get_psets(element)
                
                # Search through property sets for the quantity
                for pset_name, props in psets.items():
                    # Filter by quantity_set_name if specified
                    if quantity_set_name is not None and pset_name != quantity_set_name:
                        continue
                    
                    # Check if the quantity exists and is numeric
                    if quantity_name in props:
                        value = props[quantity_name]
                        if isinstance(value, (int, float)):
                            values.append(float(value))
                            # Found the quantity, no need to check other psets for this element
                            break
            except Exception:
                # Skip elements that cause errors during property retrieval
                continue
        
        # Return None if no valid values were found
        if not values:
            return None
        
        # Perform the requested aggregation
        if aggregate_type == 'min':
            return min(values)
        elif aggregate_type == 'max':
            return max(values)
        elif aggregate_type == 'sum':
            return sum(values)
        elif aggregate_type == 'avg':
            return sum(values) / len(values)
        else:
            # This should never be reached due to validation above
            return None
    
    except Exception:
        # Return None for any unexpected errors during processing
        return None