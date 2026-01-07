import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Any, Optional


def search_properties_by_keywords(
    model: ifcopenshell.file,
    ifc_class: str,
    keywords: List[str],
    search_in_names: bool = True,
    search_in_values: bool = True,
    pset_filter: Optional[List[str]] = None,
    element_name_attribute: str = 'Name'
) -> List[Dict[str, Any]]:
    """
    Searches for properties containing specific keywords across elements of a given IFC class.
    
    This function iterates through all elements of the specified class, examines all their 
    property sets and properties, and returns matches where property names or values contain 
    any of the specified keywords. It's useful for discovering and analyzing property data 
    when exact property names are unknown or when performing model QA for specific attributes.

    Args:
        model: The opened IFC model (ifcopenshell.file instance)
        ifc_class: The IFC class to search (e.g., 'IfcDoor', 'IfcWindow')
        keywords: List of keywords to search for in property names and values (case-insensitive)
        search_in_names: If True, searches keywords in property names (default: True)
        search_in_values: If True, searches keywords in property values (default: True)
        pset_filter: Optional list of pset names to restrict search to specific property sets
        element_name_attribute: Attribute to use for element identification (default: 'Name')

    Returns:
        List of dictionaries with matched elements and properties. Each dictionary contains:
            - 'element': element instance
            - 'element_name': str
            - 'element_id': int
            - 'pset_name': str
            - 'property_name': str
            - 'property_value': Any
            - 'matched_keyword': str

    Example usage:
        >>> model = ifcopenshell.open('model.ifc')
        >>> # Find all fire-rated elements
        >>> results = search_properties_by_keywords(
        ...     model, 'IfcDoor', ['fire', 'feuer', 'brand']
        ... )
        >>> for match in results:
        ...     print(f"{match['element_name']}: {match['property_name']} = {match['property_value']}")
        >>> 
        >>> # Find thermal properties in walls
        >>> thermal = search_properties_by_keywords(
        ...     model, 'IfcWall', ['thermal', 'insulation', 'u-value']
        ... )
    """
    results: List[Dict[str, Any]] = []
    
    try:
        # Get all elements of the specified IFC class
        elements = model.by_type(ifc_class)
    except Exception as e:
        raise ValueError(f"Failed to retrieve elements of class '{ifc_class}': {e}")
    
    # Prepare keywords for case-insensitive matching
    keywords_lower = [k.lower() for k in keywords] if keywords else []
    
    for element in elements:
        try:
            # Get element name and id
            element_name = getattr(element, element_name_attribute, 'Unknown')
            element_id = element.id()
            
            # Get all property sets for this element
            psets = ifcopenshell.util.element.get_psets(element)
            
            if not psets:
                continue
            
            # Iterate through property sets
            for pset_name, props in psets.items():
                # Apply pset filter if provided
                if pset_filter and pset_name not in pset_filter:
                    continue
                
                # Iterate through properties in the pset
                for prop_name, prop_value in props.items():
                    matched_keyword = None
                    
                    # Check property name if enabled
                    if search_in_names and keywords_lower:
                        prop_name_lower = prop_name.lower()
                        for kw in keywords_lower:
                            if kw in prop_name_lower:
                                matched_keyword = kw
                                break
                    
                    # Check property value if enabled and not already matched
                    if search_in_values and keywords_lower and matched_keyword is None:
                        value_str = str(prop_value).lower() if prop_value is not None else ''
                        for kw in keywords_lower:
                            if kw in value_str:
                                matched_keyword = kw
                                break
                    
                    # If match found, add to results
                    if matched_keyword is not None:
                        results.append({
                            'element': element,
                            'element_name': element_name,
                            'element_id': element_id,
                            'pset_name': pset_name,
                            'property_name': prop_name,
                            'property_value': prop_value,
                            'matched_keyword': matched_keyword
                        })
                    
        except Exception as e:
            # Continue with next element if there's an error processing this one
            continue
    
    return results