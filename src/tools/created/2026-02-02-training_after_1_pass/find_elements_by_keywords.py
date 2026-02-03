import ifcopenshell
from typing import List, Dict, Any, Optional, Union

def find_elements_by_keywords(
    model: ifcopenshell.file,
    entity_type: Union[str, List[str]],
    keywords: List[str],
    case_sensitive: bool = False,
    search_fields: Optional[List[str]] = None
) -> List[Dict[str, Any]]:
    """
    Finds IFC elements by searching for multiple keywords in their attributes.
    
    Performs an OR logic search - matches if ANY keyword is found in ANY of the
    specified search fields across the specified entity types.
    
    Args:
        model: The IFC model instance opened with ifcopenshell.open()
        entity_type: IFC entity type(s) to search. Can be a single string (e.g., 'IfcBuilding')
                    or a list of strings (e.g., ['IfcSanitaryTerminal', 'IfcFurnishingElement']).
        keywords: List of keywords to search for. Matches ANY keyword (OR logic).
        case_sensitive: If True, performs case-sensitive matching. Default False.
        search_fields: List of entity attributes to search. Default ['Name', 'LongName'].
    
    Returns:
        List of dictionaries, each containing:
            - 'entity': The matching IFC entity instance
            - 'name': Value of Name attribute
            - 'matched_keyword': The keyword that caused the match
            - 'matched_field': Which field contained the match
            - 'Entity_type': The specific entity type this element belongs to
            - Additional key-value pairs for each field in search_fields
    
    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> # Search single type
        >>> results = find_elements_by_keywords(
        ...     model, 'IfcBuilding', ['kirche', 'kapelle']
        ... )
        >>> # Search multiple types
        >>> results = find_elements_by_keywords(
        ...     model, 
        ...     ['IfcSanitaryTerminal', 'IfcFurnishingElement'], 
        ...     ['sink', 'toilet']
        ... )
    """
    # Validate inputs
    if not keywords:
        return []
    
    if search_fields is None:
        search_fields = ['Name', 'LongName']
    
    if not search_fields:
        return []
    
    # Normalize entity_type to a list for uniform processing
    if isinstance(entity_type, str):
        types_to_search = [entity_type]
    else:
        types_to_search = entity_type
        
    if not types_to_search:
        return []
    
    # Prepare keywords based on case sensitivity
    search_keywords = keywords if case_sensitive else [k.lower() for k in keywords]
    
    results = []
    skipped_types = 0
    skipped_elements = 0
    
    for etype in types_to_search:
        if not isinstance(etype, str) or not etype:
            skipped_types += 1
            continue
            
        try:
            # Get all elements of specified type
            elements = model.by_type(etype)
        except RuntimeError:
            # Type not found in schema, skip silently or log
            skipped_types += 1
            continue
        
        if not elements:
            continue
        
        for element in elements:
            try:
                # Collect all field values first
                field_values = {}
                for field in search_fields:
                    value = getattr(element, field, None)
                    # Convert to string, empty string if None
                    field_values[field] = str(value) if value is not None else ''
                
                # Search for keywords in any field
                matched_keyword = None
                matched_field = None
                
                for field in search_fields:
                    str_value = field_values[field]
                    search_value = str_value if case_sensitive else str_value.lower()
                    
                    for i, keyword in enumerate(search_keywords):
                        if keyword in search_value:
                            matched_keyword = keywords[i]  # Return original keyword
                            matched_field = field
                            break
                    
                    if matched_keyword is not None:
                        break
                
                # Only add results if a match was found
                if matched_keyword and matched_field:
                    # Build result dictionary
                    result = {
                        'entity': element,
                        'name': field_values.get('Name', ''),
                        'matched_keyword': matched_keyword,
                        'matched_field': matched_field,
                        'Entity_type': etype  # Add the specific entity type
                    }
                    # Add all field values
                    result.update(field_values)
                    results.append(result)
                    
            except (AttributeError, RuntimeError):
                skipped_elements += 1
                continue
    
    if skipped_types > 0:
        print(f"Warning: Skipped {skipped_types} invalid entity type(s)")
    if skipped_elements > 0:
        print(f"Warning: Skipped {skipped_elements} elements due to attribute access errors")
    
    return results