import ifcopenshell
from typing import List, Dict, Any, Optional, Union
import ifcopenshell.util.element

def find_elements_by_semantic_criteria(
    model: ifcopenshell.file,
    entity_types: List[str],
    include_keywords: List[str],
    exclude_keywords: Optional[List[str]] = None,
    group_by: str = 'ObjectType',
    return_elements: bool = False,
    case_sensitive: bool = False
) -> Dict[str, Any]:
    """
    Finds and aggregates IFC elements across multiple entity types based on semantic keyword criteria.

    This function addresses the challenge where functional equipment types (e.g., heat recovery units)
    may be modeled using different IFC entity classes (e.g., IfcBuildingElementProxy or IfcFlowTerminal).
    It combines multi-type searching, include/exclude keyword filtering, and type-based grouping.

    Args:
        model (ifcopenshell.file): The IFC model instance.
        entity_types (List[str]): IFC entity types to search (e.g., ['IfcBuildingElementProxy', 'IfcFlowTerminal']).
        include_keywords (List[str]): Keywords that indicate semantic relevance (e.g., ['HR', 'HEAT RECOVERY']).
            Elements must match at least one keyword in their Name attribute.
        exclude_keywords (Optional[List[str]]): Keywords that exclude elements from results (e.g., ['exhaust']).
            Useful for filtering false positives. Defaults to None.
        group_by (str): How to group results. Options:
            'ObjectType' (default): Uses element.ObjectType.
            'TypeObject': Uses the Name of the related Type Object (IfcRelDefinesByType).
            'Name': Uses element.Name (splits by ':' to extract base name).
        return_elements (bool): If False (default), returns only counts. If True, includes actual element instances.
        case_sensitive (bool): If False (default), performs case-insensitive keyword matching.

    Returns:
        Dict[str, Any]: A dictionary with:
            - 'counts': Dict mapping group names to their counts.
            - 'total': Total number of elements found.
            - 'elements': (optional) Dict mapping group names to lists of element instances if return_elements=True.

    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> results = find_elements_by_semantic_criteria(
        ...     model,
        ...     entity_types=['IfcBuildingElementProxy'],
        ...     include_keywords=['HR', 'HEAT RECOVERY'],
        ...     exclude_keywords=['duct'],
        ...     group_by='TypeObject'
        ... )
        >>> print(results['total'])
        1
    """
    
    if not model:
        raise ValueError("Model cannot be None")
    
    if not entity_types:
        return {'counts': {}, 'total': 0, 'elements': {}}
    
    if not include_keywords:
        raise ValueError("include_keywords cannot be empty")
    
    valid_group_by_options = ['ObjectType', 'TypeObject', 'Name']
    if group_by not in valid_group_by_options:
        raise ValueError(f"group_by must be one of {valid_group_by_options}")
    
    # Prepare keywords for matching
    if not case_sensitive:
        include_keywords = [kw.lower() for kw in include_keywords]
        if exclude_keywords:
            exclude_keywords = [kw.lower() for kw in exclude_keywords]
    
    results: Dict[str, List[ifcopenshell.entity_instance]] = {}
    skipped_elements = 0
    
    for entity_type in entity_types:
        try:
            elements = model.by_type(entity_type)
        except Exception as e:
            print(f"Warning: Could not retrieve type {entity_type}: {e}")
            continue
            
        for elem in elements:
            # Get Name safely
            elem_name = getattr(elem, 'Name', '')
            if elem_name is None: 
                elem_name = ''
            
            # Check include keywords
            name_to_check = elem_name if case_sensitive else elem_name.lower()
            if not any(kw in name_to_check for kw in include_keywords):
                continue
            
            # Check exclude keywords
            if exclude_keywords:
                if any(kw in name_to_check for kw in exclude_keywords):
                    continue
            
            # Determine Group Key
            group_key = "Unknown"
            try:
                if group_by == 'ObjectType':
                    group_key = getattr(elem, 'ObjectType', None)
                    if group_key is None:
                        group_key = "Undefined ObjectType"
                        
                elif group_by == 'TypeObject':
                    type_obj = ifcopenshell.util.element.get_type(elem)
                    if type_obj:
                        group_key = getattr(type_obj, 'Name', 'Unnamed Type')
                    else:
                        group_key = "No Type Object"
                        
                elif group_by == 'Name':
                    # Extract meaningful part of name (split by colon)
                    if elem_name:
                        name_parts = elem_name.split(':')
                        group_key = name_parts[0] if name_parts else elem_name
                    else:
                        group_key = "Unnamed"
            except AttributeError:
                skipped_elements += 1
                continue
            except RuntimeError:
                # Catch potential runtime errors during relationship traversal
                skipped_elements += 1
                continue
            
            if group_key not in results:
                results[group_key] = []
            results[group_key].append(elem)
    
    if skipped_elements > 0:
        print(f"Warning: Skipped {skipped_elements} elements due to missing attributes or access errors.")
    
    # Build output dictionary
    output: Dict[str, Any] = {
        'counts': {k: len(v) for k, v in results.items()},
        'total': sum(len(v) for v in results.values())
    }
    
    if return_elements:
        output['elements'] = results
    
    return output