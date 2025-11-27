import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional, Union

def find_elements_with_extreme_property_values(
    ifc_file: ifcopenshell.file,
    element_type: str,
    property_keywords: List[str],
    extreme_type: str = 'max',
    property_sets: Optional[List[str]] = None,
    include_overall_properties: bool = True,
    return_count: int = 10,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Finds IFC elements with extreme (maximum or minimum) values of specified properties 
    across multiple property sets using multilingual keyword matching.
    
    This function systematically explores property sets, matches property names using 
    flexible keywords, extracts numeric values safely, and returns elements sorted by 
    the target property value.
    
    Args:
        ifc_file: Loaded IFC model (ifcopenshell.file)
        element_type: IFC element type to analyze (e.g., 'IfcDoor', 'IfcWindow', 'IfcWall')
        property_keywords: List of keywords to identify target properties in multiple 
                          languages (e.g., ['width', 'breedte', 'lengte'])
        extreme_type: 'max' or 'min' to find maximum or minimum values
        property_sets: Optional list of property sets to prioritize (searches all if None)
        include_overall_properties: Boolean to check direct element properties like 
                                   OverallWidth/OverallHeight (default: True)
        return_count: Number of top results to return (default: 10)
        case_sensitive: Boolean for keyword matching (default: False)
    
    Returns:
        Dict with 'elements' list sorted by extreme value, each containing id, name, 
        value, and source information.
        
    Example:
        >>> model = ifcopenshell.open('building.ifc')
        >>> result = find_elements_with_extreme_property_values(
        ...     model, 'IfcDoor', ['width', 'breedte'], 'max'
        ... )
        >>> print(result['elements'][0])  # Widest door
    """
    
    if extreme_type not in ['max', 'min']:
        raise ValueError("extreme_type must be 'max' or 'min'")
    
    # Get all elements of the specified type
    elements = ifc_file.by_type(element_type)
    if not elements:
        return {'elements': [], 'total_analyzed': 0}
    
    # Prepare keywords for matching
    if not case_sensitive:
        property_keywords = [kw.lower() for kw in property_keywords]
    
    elements_with_values = []
    
    for element in elements:
        best_value = None
        best_source = None
        
        # Check property sets
        try:
            psets = ifcopenshell.util.element.get_psets(element)
            
            for pset_name, pset_data in psets.items():
                # Skip if property_sets is specified and this pset is not in it
                if property_sets and pset_name not in property_sets:
                    continue
                
                for prop_name, prop_value in pset_data.items():
                    # Check if property name matches any keyword
                    prop_name_check = prop_name if case_sensitive else prop_name.lower()
                    
                    keyword_match = any(
                        keyword in prop_name_check 
                        for keyword in property_keywords
                    )
                    
                    if keyword_match:
                        try:
                            # Extract numeric value
                            if isinstance(prop_value, (int, float)):
                                numeric_value = float(prop_value)
                            elif hasattr(prop_value, 'wrappedValue'):
                                numeric_value = float(prop_value.wrappedValue)
                            else:
                                continue
                            
                            # Update if this is a better match
                            if best_value is None:
                                best_value = numeric_value
                                best_source = f"{pset_name}.{prop_name}"
                            elif extreme_type == 'max' and numeric_value > best_value:
                                best_value = numeric_value
                                best_source = f"{pset_name}.{prop_name}"
                            elif extreme_type == 'min' and numeric_value < best_value:
                                best_value = numeric_value
                                best_source = f"{pset_name}.{prop_name}"
                                
                        except (ValueError, TypeError, AttributeError):
                            continue
                            
        except Exception:
            # Continue if property access fails
            pass
        
        # Check direct element properties if requested
        if include_overall_properties:
            overall_props = ['OverallWidth', 'OverallHeight', 'OverallDepth', 'Length', 'Width', 'Height']
            
            for prop_name in overall_props:
                if hasattr(element, prop_name):
                    prop_value = getattr(element, prop_name)
                    if prop_value is not None:
                        try:
                            numeric_value = float(prop_value)
                            
                            if best_value is None:
                                best_value = numeric_value
                                best_source = prop_name
                            elif extreme_type == 'max' and numeric_value > best_value:
                                best_value = numeric_value
                                best_source = prop_name
                            elif extreme_type == 'min' and numeric_value < best_value:
                                best_value = numeric_value
                                best_source = prop_name
                                
                        except (ValueError, TypeError):
                            continue
        
        # Add element if we found a value
        if best_value is not None:
            elements_with_values.append({
                'id': element.id(),
                'name': getattr(element, 'Name', None),
                'value': best_value,
                'source': best_source,
                'object_type': getattr(element, 'ObjectType', None)
            })
    
    # Sort by extreme value
    reverse_sort = (extreme_type == 'max')
    sorted_elements = sorted(
        elements_with_values, 
        key=lambda x: x['value'], 
        reverse=reverse_sort
    )
    
    # Return top results
    return {
        'elements': sorted_elements[:return_count],
        'total_analyzed': len(elements),
        'elements_with_values': len(elements_with_values),
        'extreme_type': extreme_type
    }