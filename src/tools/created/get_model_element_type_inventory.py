import ifcopenshell
from typing import Dict, Any, List, Optional


def get_model_element_type_inventory(
    model: ifcopenshell.file,
    sort_by: str = 'count',
    filter_pattern: Optional[str] = None,
    include_keywords: Optional[List[str]] = None,
    exclude_keywords: Optional[List[str]] = None,
    include_type_list: Optional[List[str]] = None,
    include_ids: bool = False,
    top_n: Optional[int] = None,
    keywords_match_mode: str = 'or',
    keywords_case_sensitive: bool = False
) -> Dict[str, Dict[str, Any]]:
    """
    Generates a comprehensive inventory of all IFC element types present in the model with their instance counts.
    This function is ideal for initial model exploration to understand the schema version, what building systems
    are represented, and which element types are available for further querying.

    Args:
        model: The loaded IFC model instance (ifcopenshell.file)
        sort_by: Optional sorting method - 'count' (default), 'name', or None for unsorted
        filter_pattern: Optional string pattern to filter type names (e.g., 'Flow', 'Distribution', 'System').
                      Note: This parameter interacts with keywords_case_sensitive for its matching logic.
        include_keywords: Optional list of keywords. Only includes IFC types where the type name matches these keywords.
        exclude_keywords: Optional list of keywords. Excludes IFC types where the type name matches these keywords.
                              Takes precedence over include_keywords.
        include_type_list: Optional list of IFC type names. If provided, filters the resulting inventory to include 
                           only those IFC types that are present in both the model and the provided list. 
                           Matching is exact (substring matching is not applied here, unlike include_keywords).
        include_ids: If True, includes sample instance IDs for each type (default: False)
        top_n: Optional limit on number of types returned (default: None for all)
        keywords_match_mode: Determines how multiple keywords are combined. 'and' requires all keywords to match, 
                             'or' requires any keyword to match. Defaults to 'or'.
        keywords_case_sensitive: If False (default), performs case-insensitive keyword matching. 
                                 Defaults to False.

    Returns:
        Dict[str, Dict[str, Any]]: A dictionary keyed by IFC type name, where each value contains:
            - 'count': Number of instances of this type
            - 'sample_ids': (optional) List of up to 5 instance GlobalIds

    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> # Check for specific MEP types (e.g., Pipes and Ducts)
        >>> inventory = get_model_element_type_inventory(model, include_type_list=['IfcPipeSegment', 'IfcDuctSegment'])
        >>> # Get all structural elements (using keywords)
        >>> inventory = get_model_element_type_inventory(model, include_keywords=['Wall', 'Column', 'Beam'])
    """
    # Validate inputs
    if model is None:
        raise ValueError("Model cannot be None")
    
    if keywords_match_mode not in ['and', 'or']:
        raise ValueError("keywords_match_mode must be 'and' or 'or'")

    # Normalize keyword lists based on case sensitivity setting
    include_kw_processed = include_keywords
    exclude_kw_processed = exclude_keywords
    include_type_list_processed = include_type_list
    
    if not keywords_case_sensitive:
        # Convert keywords to lowercase for case-insensitive matching
        include_kw_processed = [k.lower() for k in include_keywords] if include_keywords else None
        exclude_kw_processed = [k.lower() for k in exclude_keywords] if exclude_keywords else None
        # Convert type list to lowercase for case-insensitive matching (exact match on lowercased strings)
        include_type_list_processed = [t.lower() for t in include_type_list] if include_type_list else None

    # Build inventory dictionary
    inventory: Dict[str, Dict[str, Any]] = {}
    skipped_elements = 0
    
    for elem in model:
        try:
            elem_type = elem.is_a()
        except (AttributeError, RuntimeError):
            skipped_elements += 1
            continue
        
        # Prepare element type for comparison
        elem_type_processed = elem_type if keywords_case_sensitive else elem_type.lower()

        # 0. Apply include_type_list filter (Exact match required)
        # If a list is provided, the type MUST be in it.
        if include_type_list_processed:
            if elem_type_processed not in include_type_list_processed:
                continue

        # 1. Apply legacy filter_pattern if provided
        if filter_pattern:
            # Normalize pattern check based on case sensitivity setting
            pattern_check = filter_pattern if keywords_case_sensitive else filter_pattern.lower()
            if pattern_check not in elem_type_processed:
                continue

        # 2. Apply semantic filtering
        
        # Check exclude keywords (Precedence)
        if exclude_kw_processed:
            if keywords_match_mode == 'and':
                # Exclude only if ALL keywords match
                if all(kw in elem_type_processed for kw in exclude_kw_processed):
                    continue
            else:  # 'or'
                # Exclude if ANY keyword matches
                if any(kw in elem_type_processed for kw in exclude_kw_processed):
                    continue

        # Check include keywords
        if include_kw_processed:
            if keywords_match_mode == 'and':
                # Include only if ALL keywords match
                if not all(kw in elem_type_processed for kw in include_kw_processed):
                    continue
            else:  # 'or'
                # Include if ANY keyword matches
                if not any(kw in elem_type_processed for kw in include_kw_processed):
                    continue
        
        # Initialize type entry if not exists
        if elem_type not in inventory:
            inventory[elem_type] = {'count': 0}
            if include_ids:
                inventory[elem_type]['sample_ids'] = []
        
        # Increment count
        inventory[elem_type]['count'] += 1
        
        # Collect sample IDs if requested (up to 5 per type)
        if include_ids:
            try:
                global_id = getattr(elem, 'GlobalId', None)
                if global_id and len(inventory[elem_type]['sample_ids']) < 5:
                    inventory[elem_type]['sample_ids'].append(global_id)
            except AttributeError:
                pass  # Skip elements without GlobalId
    
    # Sort the inventory
    if sort_by == 'count':
        sorted_items = sorted(inventory.items(), key=lambda x: x[1]['count'], reverse=True)
    elif sort_by == 'name':
        sorted_items = sorted(inventory.items(), key=lambda x: x[0])
    else:  # unsorted
        sorted_items = list(inventory.items())
    
    # Apply top_n limit
    if top_n is not None:
        sorted_items = sorted_items[:top_n]
    
    # Rebuild dictionary with sorted items
    result: Dict[str, Dict[str, Any]] = {k: v for k, v in sorted_items}
    
    return result