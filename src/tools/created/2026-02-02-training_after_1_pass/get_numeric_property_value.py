import ifcopenshell
import ifcopenshell.util.element
from typing import List, Optional, Union, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    import ifcopenshell

def get_numeric_property_value(
    model: ifcopenshell.file,
    element_type: Optional[str] = None,
    element: Optional['ifcopenshell.entity_instance'] = None,
    pset_name: str = '',
    property_name: str = '',
    default: Optional[float] = None,
    aggregation: Literal['first', 'all', 'list'] = 'first'
) -> Union[float, List[float], None]:
    """
    Extracts numeric property values from IFC elements, handling both IfcPropertySet and IfcElementQuantity.

    This function retrieves a property value from a specific Property Set (Pset) or Element Quantity.
    It automatically converts IfcMeasure types (like IfcLengthMeasure, IfcAreaMeasure) to native Python
    numeric types by accessing the .wrappedValue attribute. It first checks PropertySets, and falls back
    to ElementQuantities if the property is not found.

    Args:
        model: The IFC model instance
        element_type: IFC entity type to search (e.g., 'IfcWall'). If None, a single element
            must be provided.
        element: Single element to query. If provided, element_type is ignored.
        pset_name: Name of the Property Set (or Element Quantity) containing the property/quantity.
        property_name: Name of the property (or quantity) to extract.
        default: Default value if property is not found or cannot be converted. Defaults to None.
        aggregation: How to return values:
            - 'first': returns a single value (first found)
            - 'all': returns a list of all values
            - 'list': alias for 'all'

    Returns:
        A single numeric value, list of values, or default value if not found.

    Raises:
        ValueError: If neither element_type nor element is provided.

    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> # Get floor area from BaseQuantities (ElementQuantity)
        >>> area = get_numeric_property_value(
        ...     model,
        ...     element_type='IfcSpace',
        ...     pset_name='BaseQuantities',
        ...     property_name='NetFloorArea'
        ... )
        >>> print(area)  # 23.9
    """
    # Validate inputs
    if element is None and element_type is None:
        raise ValueError("Either 'element' or 'element_type' must be provided")

    # Normalize aggregation mode
    if aggregation == 'list':
        aggregation = 'all'

    # Determine which elements to query
    if element is not None:
        elements = [element]
    else:
        elements = model.by_type(element_type)
        if not elements:
            return default if aggregation == 'first' else []

    # Map quantity types to their value attributes
    quantity_attribute_map = {
        'IfcQuantityArea': 'AreaValue',
        'IfcQuantityLength': 'LengthValue',
        'IfcQuantityVolume': 'VolumeValue',
        'IfcQuantityWeight': 'WeightValue',
        'IfcQuantityTime': 'TimeValue',
        'IfcQuantityCount': 'CountValue'
    }

    # Collect values from elements
    values = []
    skipped = 0

    for elem in elements:
        found_value = None
        
        # Attempt 1: Standard Property Set (IfcPropertySet)
        try:
            value = ifcopenshell.util.element.get_pset(
                elem, 
                name=pset_name, 
                prop=property_name,
                psets_only=True, 
                should_inherit=True
            )

            if value is not None:
                # Check if value is an IfcMeasure type with wrappedValue
                if hasattr(value, 'wrappedValue'):
                    numeric_value = value.wrappedValue
                    if isinstance(numeric_value, (int, float)):
                        found_value = float(numeric_value)
                elif isinstance(value, (int, float)):
                    found_value = float(value)
        except (AttributeError, KeyError):
            pass

        # Attempt 2: Element Quantities (IfcElementQuantity) - Fallback
        if found_value is None:
            try:
                # Iterate through IsDefinedBy relationships
                for rel in elem.IsDefinedBy:
                    # Ensure it's a property relationship
                    if not rel.is_a('IfcRelDefinesByProperties'):
                        continue
                    
                    if not hasattr(rel, 'RelatingPropertyDefinition'):
                        continue
                    
                    pdef = rel.RelatingPropertyDefinition
                    
                    # Check if it's an Element Quantity with the matching name
                    if pdef.is_a('IfcElementQuantity') and pdef.Name == pset_name:
                        if hasattr(pdef, 'Quantities'):
                            for qty in pdef.Quantities:
                                if qty.Name == property_name:
                                    # Determine the correct attribute based on quantity type
                                    qty_type = qty.is_a()
                                    attr_name = quantity_attribute_map.get(qty_type)
                                    
                                    if attr_name and hasattr(qty, attr_name):
                                        raw_val = getattr(qty, attr_name)
                                        
                                        # Handle IfcMeasure wrappers or direct values
                                        if hasattr(raw_val, 'wrappedValue'):
                                            val = raw_val.wrappedValue
                                        elif isinstance(raw_val, (int, float)):
                                            val = raw_val
                                        else:
                                            continue # Skip non-numeric
                                            
                                        found_value = float(val)
                                        break # Found the quantity, stop inner loop
                            if found_value is not None:
                                break # Found the quantity, stop outer loop
            except (AttributeError, RuntimeError):
                # If traversing quantities fails, we just skip this element
                pass

        if found_value is not None:
            values.append(found_value)
        else:
            skipped += 1

    # Report data loss if applicable
    if skipped > 0:
        print(f"Warning: Skipped {skipped} elements (property not found or not numeric)")

    # Return based on aggregation mode
    if aggregation == 'first':
        return values[0] if values else default
    else:  # 'all'
        return values if values else []