import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, Any, Callable, Optional, Union

def get_element_counts_with_fallback(
    model: ifcopenshell.file, 
    element_type: str, 
    fallback_attribute: str = 'ObjectType', 
    untyped_threshold: float = 0.9,
    undefined_threshold: float = 0.9,
    pattern_func: Optional[Callable[[str], Optional[str]]] = None,
    pattern_default: str = 'Other',
    sort_descending: bool = True
) -> Dict[str, int]:
    """
    Groups and counts IFC elements by their type, employing a robust multi-level 
    fallback strategy for models with inconsistent type definitions.

    This function attempts to classify elements using a cascading strategy:
    1. Standard Type Object classification (via IsTypedBy relationship)
    2. Fallback attribute classification (e.g., ObjectType, PredefinedType)
    3. Name pattern extraction (if pattern_func is provided)

    To handle cases where attributes contain instance-specific data (e.g. 
    'TypeName:12345'), the key is sanitized by splitting on the first colon and 
    retaining the prefix, which is typically the actual type name.

    Args:
        model: The IFC model instance.
        element_type: IFC entity type to analyze (e.g., 'IfcBeam', 'IfcWallStandardCase').
        fallback_attribute: The entity attribute to use if standard Type Objects fail 
                           (e.g., 'ObjectType', 'PredefinedType', 'Name'). Defaults to 'ObjectType'.
        untyped_threshold: The ratio of 'Untyped' elements required to trigger the 
                           fallback from Type Objects to fallback_attribute (0.0 to 1.0). 
                           Defaults to 0.9.
        undefined_threshold: The ratio of 'Undefined' elements from fallback_attribute 
                             required to trigger pattern extraction (if pattern_func provided).
                             Only used when pattern_func is not None. Defaults to 0.9.
        pattern_func: Optional callable that extracts type from element name.
                      Accepts element name (str) and returns extracted type (str), or None
                      to use pattern_default. Useful for parsing prefixes, codes, or regex.
        pattern_default: Label for elements where pattern_func returns None. 
                         Defaults to 'Other'.
        sort_descending: If True, sorts the results by count in descending order.

    Returns:
        Dict[str, int]: A dictionary mapping type names to their respective counts.
    
    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> # Standard usage with Type Objects
        >>> counts = get_element_counts_with_fallback(model, 'IfcBeam')
        >>> # Pattern extraction from names (e.g., extract 'trappen' from 'trappen_(#123)')
        >>> def extract_stair_type(name):
        ...     if name and '_' in name:
        ...         return name.split('_')[0]
        ...     return None
        >>> counts = get_element_counts_with_fallback(
        ...     model, 'IfcStair', pattern_func=extract_stair_type
        ... )
        >>> print(counts)
        {'trappen': 6, 'trapbordes': 3}
    """
    # 1. Retrieve elements
    elements = model.by_type(element_type)
    
    if not elements:
        return {}
    
    # 2. Attempt classification by Standard Type Object (IsTypedBy)
    type_object_counts: Dict[str, int] = {}
    untyped_count = 0
    
    for element in elements:
        try:
            type_obj = ifcopenshell.util.element.get_type(element)
            if type_obj is not None:
                # Use the Type Object's Name. If missing, use a generated name.
                key = getattr(type_obj, 'Name', None)
                if key is None:
                    key = f"UnnamedType_{type_obj.id()}"
            else:
                key = "Untyped"
                untyped_count += 1
        except RuntimeError:
            # Handle potential errors in type resolution
            key = "Error"
            untyped_count += 1
            
        type_object_counts[key] = type_object_counts.get(key, 0) + 1
    
    # 3. Check if fallback is necessary
    total_elements = len(elements)
    untyped_ratio = untyped_count / total_elements if total_elements > 0 else 0.0
    
    if untyped_ratio < untyped_threshold:
        # Type Object classification was successful enough
        result = type_object_counts
    else:
        # Fallback Strategy: Group by attribute
        final_counts: Dict[str, int] = {}
        undefined_count = 0
        
        for element in elements:
            # Safely get the attribute value
            raw_val = getattr(element, fallback_attribute, None)
            
            if raw_val is None:
                key = "Undefined"
                undefined_count += 1
            else:
                # Sanitize the key: remove instance-specific IDs often found after a colon
                # e.g. "TypeA:12345" -> "TypeA"
                str_val = str(raw_val)
                if ':' in str_val:
                    key = str_val.split(':', 1)[0]
                else:
                    key = str_val
            
            final_counts[key] = final_counts.get(key, 0) + 1
        
        # 4. Check if pattern extraction should be used
        undefined_ratio = undefined_count / total_elements if total_elements > 0 else 0.0
        
        if pattern_func is not None and undefined_ratio >= undefined_threshold:
            # Pattern extraction from names
            pattern_counts: Dict[str, int] = {}
            pattern_skipped = 0
            
            for element in elements:
                name = getattr(element, 'Name', None)
                
                try:
                    extracted = pattern_func(name) if name is not None else None
                    
                    if extracted is not None:
                        key = extracted
                    else:
                        key = pattern_default
                        pattern_skipped += 1
                except (AttributeError, TypeError, ValueError):
                    # Handle errors from pattern_func gracefully
                    key = pattern_default
                    pattern_skipped += 1
                
                pattern_counts[key] = pattern_counts.get(key, 0) + 1
            
            if pattern_skipped > 0:
                print(f"Warning: Pattern extraction assigned {pattern_skipped} elements to '{pattern_default}'.")
            
            result = pattern_counts
        else:
            if undefined_count > 0:
                print(f"Warning: Skipped {undefined_count} elements due to missing '{fallback_attribute}' attribute.")
            result = final_counts
    
    # 5. Sort results if requested
    if sort_descending:
        result = dict(sorted(result.items(), key=lambda item: item[1], reverse=True))
        
    return result