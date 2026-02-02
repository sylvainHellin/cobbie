import ifcopenshell
from typing import List


def filter_elements_by_name_patterns(
    model: ifcopenshell.file,
    entity_type: str,
    include_patterns: List[str],
    exclude_patterns: List[str],
    case_sensitive: bool = False,
    search_attributes: List[str] = ['Name']
) -> List[ifcopenshell.entity_instance]:
    """
    Filters IFC elements of a specific type based on inclusion and exclusion patterns in their string attributes.
    This function abstracts the common pattern of semantic filtering when category information is
    encoded in naming conventions rather than explicit IFC type systems or property sets.

    Args:
        model (ifcopenshell.file): The IFC model instance
        entity_type (str): IFC entity type to filter (e.g., 'IfcBuilding', 'IfcDoor', 'IfcSpace')
        include_patterns (List[str]): List of substrings - element must contain at least one (OR logic).
                                        Empty list means no inclusion filter.
        exclude_patterns (List[str]): List of substrings - element must not contain any (AND logic).
                                        Empty list means no exclusion filter.
        case_sensitive (bool): Whether string matching is case sensitive. Defaults to False.
        search_attributes (List[str]): Which attributes to check against. Defaults to ['Name'].
                                        Can include 'LongName', 'Description'.

    Returns:
        List[ifcopenshell.entity_instance]: Filtered list of elements matching all criteria.
                                            Returns empty list if entity_type is invalid or no elements found.

    Example usage:
        >>> model = ifcopenshell.open('city.ifc')
        >>> # Find town gates excluding towers
        >>> gates = filter_elements_by_name_patterns(
        ...     model, 'IfcBuilding',
        ...     include_patterns=['Tor'],
        ...     exclude_patterns=['Torturm']
        ... )
        >>> [g.Name for g in gates]
        ['Unteres-Tor', 'Oberes-Tor', 'Ringsheimer-Tor']
    """
    # Validate inputs
    if not model:
        return []
    
    if not entity_type:
        return []
    
    # Normalize patterns if case-insensitive
    if not case_sensitive:
        normalized_include = [p.lower() for p in include_patterns]
        normalized_exclude = [p.lower() for p in exclude_patterns]
    else:
        normalized_include = include_patterns
        normalized_exclude = exclude_patterns
    
    # Get all elements of the specified type
    try:
        elements = model.by_type(entity_type)
    except RuntimeError:
        # Entity type does not exist in the schema
        return []
    
    if not elements:
        return []
    
    result = []
    skipped = 0
    
    for element in elements:
        try:
            # Collect all attribute values to search
            search_values = []
            for attr in search_attributes:
                # Use getattr with None as default for optional attributes
                value = getattr(element, attr, None)
                if value is not None:
                    search_values.append(str(value))
            
            # Skip if no attributes found
            if not search_values:
                skipped += 1
                continue
            
            # Combine all search values for checking
            combined_text = ' '.join(search_values)
            
            # Apply case insensitivity if needed
            check_text = combined_text if case_sensitive else combined_text.lower()
            
            # Check inclusion patterns (OR logic - must match at least one)
            if normalized_include:
                include_match = any(pattern in check_text for pattern in normalized_include)
            else:
                include_match = True  # No inclusion filter = all pass
            
            # Check exclusion patterns (AND logic - must not match any)
            if normalized_exclude:
                exclude_match = any(pattern in check_text for pattern in normalized_exclude)
            else:
                exclude_match = False  # No exclusion filter = none fail
            
            # Element passes if it matches inclusion and doesn't match exclusion
            if include_match and not exclude_match:
                result.append(element)
                
        except (AttributeError, TypeError) as e:
            # Skip elements that cause attribute access errors
            skipped += 1
            continue
    
    if skipped > 0:
        print(f"Warning: Skipped {skipped} elements due to missing attributes or access errors")
    
    return result