import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, Optional, Any, Callable

def get_element_counts_by_type_object(
    model: ifcopenshell.file,
    element_type: str,
    type_attribute: str = "Name",
    default_type_name: str = "Untyped",
    pset_name: Optional[str] = None,
    property_name: Optional[str] = None,
    property_value: Optional[Any] = None,
    comparator: Optional[Callable[[Any], bool]] = None
) -> Dict[str, int]:
    """
    Groups and counts IFC elements by their associated Type Object, with optional filtering by Property Set values.

    This function retrieves elements of a specified IFC type, optionally filters them based on
    Property Set criteria, and then groups them by their Type Object (via IsTypedBy or IsDefinedBy
    relationships depending on IFC schema version).
    
    The function supports both IFC2X3 (using IsDefinedBy) and IFC4+ (using IsTypedBy) schemas by
    checking both relationship types to find Type Objects.

    Args:
        model: The IFC model instance.
        element_type: IFC entity type to analyze (e.g., 'IfcColumn', 'IfcWall', 'IfcDoor').
        type_attribute: The attribute of the Type Object to group by. Defaults to 'Name'.
        default_type_name: Label to use for elements without Type associations. Defaults to 'Untyped'.
        pset_name: Name of Property Set to filter on (e.g., 'Pset_WallCommon'). Default: None.
        property_name: Name of property within Pset to filter on (e.g., 'IsExternal'). Default: None.
        property_value: Value to match for the property (e.g., False). Default: None.
        comparator: Custom comparison function for more complex filtering (e.g., lambda x: x > 60). Default: None.
                     If provided, this takes precedence over property_value.

    Returns:
        A dictionary mapping Type Object attribute values to their element counts.
        Returns an empty dictionary if no elements are found or if the input is invalid.

    Example Usage:
        # Count all wall types
        >>> model = ifcopenshell.open('model.ifc')
        >>> counts = get_element_counts_by_type_object(model, 'IfcWall')
        >>> print(counts)
        {'Basiswand:STB 15.0 - Sichtbeton': 56, 'OtherType': 10}

        # Count only exterior wall types (IsExternal = True)
        >>> exterior_counts = get_element_counts_by_type_object(
        ...     model, 'IfcWall', 
        ...     pset_name='Pset_WallCommon', 
        ...     property_name='IsExternal', 
        ...     property_value=True
        ... )
        >>> print(exterior_counts)
        {'Basiswand:STB 15.0 - Sichtbeton': 56, 'Basiswand:MW 15cm 2': 12}

        # Count walls with custom comparator
        >>> thick_walls = get_element_counts_by_type_object(
        ...     model, 'IfcWall',
        ...     pset_name='Pset_WallCommon',
        ...     property_name='Thickness',
        ...     comparator=lambda x: x > 0.3
        ... )
    """
    # Input validation
    if model is None:
        return {}
    if not element_type or not isinstance(element_type, str):
        return {}

    # Retrieve elements
    elements = model.by_type(element_type)
    if not elements:
        return {}

    # Check if filtering is active (requires both pset_name and property_name)
    is_filtering = pset_name is not None and property_name is not None

    counts: Dict[str, int] = {}
    skipped = 0
    processed_count = 0

    def get_type_object_value(elem: ifcopenshell.entity_instance) -> Optional[str]:
        """
        Extract type object value from an element, supporting both IFC2X3 and IFC4+.
        
        This helper function tries multiple relationship paths to find the Type Object:
        1. IsTypedBy (IFC4+)
        2. IsDefinedBy (IFC2X3) - specifically looking for IfcRelDefinesByType
        
        Returns:
            The string value of the requested type_attribute, or None if not found.
        """
        # Try IsTypedBy first (IFC4+)
        is_typed_by_rels = getattr(elem, 'IsTypedBy', None)
        if is_typed_by_rels:
            for rel in is_typed_by_rels:
                if hasattr(rel, 'RelatingType'):
                    type_obj = rel.RelatingType
                    if type_obj and hasattr(type_obj, type_attribute):
                        val = getattr(type_obj, type_attribute)
                        if val is not None:
                            return str(val)
        
        # Fall back to IsDefinedBy (IFC2X3)
        # In IFC2X3, type relationships are via IsDefinedBy, but we need to filter
        # specifically for IfcRelDefinesByType (not IfcRelDefinesByProperties)
        is_defined_by_rels = getattr(elem, 'IsDefinedBy', None)
        if is_defined_by_rels:
            for rel in is_defined_by_rels:
                # Check if this is a type relationship, not a property relationship
                if rel.is_a('IfcRelDefinesByType') and hasattr(rel, 'RelatingType'):
                    type_obj = rel.RelatingType
                    if type_obj and hasattr(type_obj, type_attribute):
                        val = getattr(type_obj, type_attribute)
                        if val is not None:
                            return str(val)
        
        return None

    for elem in elements:
        try:
            # Filtering Logic - skip elements that don't match criteria
            if is_filtering:
                # Get all property sets for the element
                psets = ifcopenshell.util.element.get_psets(elem)
                
                # Check if Pset exists
                if pset_name not in psets:
                    continue  # Element doesn't have the Pset, skip it (filter out)
                
                # Check if Property exists
                pset_properties = psets[pset_name]
                if property_name not in pset_properties:
                    continue  # Element doesn't have the Property, skip it (filter out)
                
                actual_value = pset_properties[property_name]
                
                # Check match using comparator or direct equality
                match = False
                if comparator is not None:
                    try:
                        if comparator(actual_value):
                            match = True
                    except Exception:
                        # If comparator fails, treat as no match
                        continue
                elif actual_value == property_value:
                    match = True
                
                if not match:
                    continue  # Element doesn't match criteria, skip it

            # Type Object Grouping Logic
            # Use helper function to get type value (supports both IFC2X3 and IFC4+)
            found_type_value = get_type_object_value(elem)
            
            # Determine the key for grouping
            type_key = found_type_value if found_type_value is not None else default_type_name
            
            counts[type_key] = counts.get(type_key, 0) + 1
            processed_count += 1

        except (AttributeError, KeyError, RuntimeError):
            skipped += 1
            continue

    # Report data loss if any occurred
    if skipped > 0:
        print(f"Warning: Processed {processed_count}/{len(elements)} elements, {skipped} skipped due to errors.")

    return counts