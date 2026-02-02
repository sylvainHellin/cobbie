import ifcopenshell
from typing import List, Dict, Any, Optional, Union


def categorize_elements_semantically(
    model: ifcopenshell.file,
    element_type: str,
    category_definitions: Dict[str, Dict[str, List[str]]],
    search_attributes: List[str] = ['Name', 'ObjectType', 'Description'],
    case_sensitive: bool = False,
    return_uncategorized: bool = True
) -> Dict[str, List[ifcopenshell.entity_instance]]:
    """
    Categorizes IFC elements into semantic categories based on keyword matching rules.
    
    This function addresses the common pattern where generic element types 
    (e.g., IfcBuildingElementProxy) need to be classified into their functional 
    meaning based on naming conventions, ObjectType, or other string attributes.
    
    Args:
        model: The IFC model instance
        element_type: IFC entity type to categorize (e.g., 'IfcBuildingElementProxy')
        category_definitions: Dictionary mapping category names to their keyword rules:
            {'CategoryName': {'include': ['keyword1', 'keyword2'], 'exclude': ['badword']}, ...}
            Elements are assigned to the first matching category in definition order
        search_attributes: List of attributes to search in (default: ['Name', 'ObjectType', 'Description'])
        case_sensitive: Whether keyword matching is case-sensitive (default: False)
        return_uncategorized: Whether to include 'Uncategorized' key for unmatched elements (default: True)
    
    Returns:
        Dictionary mapping category names to lists of element instances. 
        If return_uncategorized is True, includes an 'Uncategorized' key for 
        elements that didn't match any category.
    
    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> definitions = {
        ...     'Plumbing': {'include': ['afvoer', 'drain', 'plumbing']},
        ...     'Mailboxes': {'include': ['brievenbus', 'mailbox'], 'exclude': ['table']},
        ...     'Ventilation': {'include': ['rooster', 'vent', 'grille']}
        ... }
        >>> results = categorize_elements_semantically(
        ...     model, 'IfcBuildingElementProxy', definitions
        ... )
        >>> print(f"Plumbing fixtures: {len(results['Plumbing'])}")
        >>> print(f"Mailboxes: {len(results['Mailboxes'])}")
    """
    # Validate inputs
    if model is None:
        raise ValueError("model cannot be None")
    
    if not element_type:
        raise ValueError("element_type cannot be empty")
    
    if not category_definitions:
        raise ValueError("category_definitions cannot be empty")
    
    # Initialize result dictionary
    result: Dict[str, List[ifcopenshell.entity_instance]] = {}
    for category_name in category_definitions.keys():
        result[category_name] = []
    
    if return_uncategorized:
        result['Uncategorized'] = []
    
    # Get elements of specified type
    try:
        elements = model.by_type(element_type)
    except RuntimeError as e:
        raise RuntimeError(f"Invalid element type '{element_type}': {e}")
    
    if not elements:
        return result
    
    # Process each element
    for elem in elements:
        try:
            # Collect attribute values to search in
            search_text_parts = []
            
            for attr in search_attributes:
                try:
                    value = getattr(elem, attr, None)
                    if value is not None:
                        # Convert to string and handle case sensitivity
                        text = str(value)
                        if not case_sensitive:
                            text = text.lower()
                        search_text_parts.append(text)
                except AttributeError:
                    # Attribute doesn't exist for this element type, skip it
                    continue
            
            # Combine all search text
            combined_text = ' '.join(search_text_parts)
            
            if not combined_text.strip():
                # No searchable content, mark as uncategorized if enabled
                if return_uncategorized:
                    result['Uncategorized'].append(elem)
                continue
            
            # Try to match against each category in order
            matched = False
            
            for category_name, rules in category_definitions.items():
                include_keywords = rules.get('include', [])
                exclude_keywords = rules.get('exclude', [])
                
                if not include_keywords:
                    # No include rules, skip this category
                    continue
                
                # Check include keywords
                include_match = False
                for keyword in include_keywords:
                    search_keyword = keyword if case_sensitive else keyword.lower()
                    if search_keyword in combined_text:
                        include_match = True
                        break
                
                if not include_match:
                    # Didn't match include keywords, try next category
                    continue
                
                # Check exclude keywords (only if include matched)
                exclude_match = False
                for keyword in exclude_keywords:
                    search_keyword = keyword if case_sensitive else keyword.lower()
                    if search_keyword in combined_text:
                        exclude_match = True
                        break
                
                if exclude_match:
                    # Matched exclude keyword, try next category
                    continue
                
                # Found a match
                result[category_name].append(elem)
                matched = True
                break  # Stop checking categories (first match wins)
            
            # If no category matched, add to uncategorized
            if not matched and return_uncategorized:
                result['Uncategorized'].append(elem)
            
        except Exception:
            # Skip element but continue processing others
            continue
    
    return result