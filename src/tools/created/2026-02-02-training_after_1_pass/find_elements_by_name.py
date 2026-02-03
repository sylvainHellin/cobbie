import ifcopenshell
from typing import List

def find_elements_by_name(
    model: ifcopenshell.file,
    entity_type: str,
    search_term: str,
    exact_match: bool = False
) -> List[ifcopenshell.entity_instance]:
    """
    Finds IFC elements by searching for a substring in their Name or LongName attributes.
    
    This function abstracts the common pattern of locating elements where the friendly name
    might be stored in LongName while Name contains an ID, or vice versa. It's useful for
    finding spaces, storeys, zones, or any named element when the exact attribute containing
    the name is unknown.
    
    Args:
        model: The IFC model instance
        entity_type: IFC entity type to search (e.g., 'IfcSpace', 'IfcBuildingStorey')
        search_term: Substring to search for in Name or LongName attributes (case-insensitive)
        exact_match: If True, requires exact string match instead of substring. Defaults to False.
    
    Returns:
        List of matching entities (may be empty if no matches found or if inputs are invalid)
    
    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> rooms = find_elements_by_name(model, 'IfcSpace', '112')
        >>> print(f"Found {len(rooms)} rooms matching '112'")
        Found 1 rooms matching '112'
        >>> space = rooms[0]
        >>> print(f"Name: {space.Name}, LongName: {space.LongName}")
        Name: 112, LongName: MASTER BEDROOM
    """
    # Input validation
    if not model:
        return []
    
    if not search_term:
        return []
    
    # Get all elements of the specified type
    elements = model.by_type(entity_type)
    matches = []
    
    for elem in elements:
        # Defensive attribute access with defaults
        name = getattr(elem, 'Name', None)
        long_name = getattr(elem, 'LongName', None)
        
        if exact_match:
            # Exact match comparison
            if (name is not None and name == search_term) or \
               (long_name is not None and long_name == search_term):
                matches.append(elem)
        else:
            # Substring match comparison (case-insensitive)
            search_lower = search_term.lower()
            if (name is not None and search_lower in name.lower()) or \
               (long_name is not None and search_lower in long_name.lower()):
                matches.append(elem)
    
    return matches