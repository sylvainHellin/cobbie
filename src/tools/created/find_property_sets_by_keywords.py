import ifcopenshell
from typing import List, Dict, Union, Any

def find_property_sets_by_keywords(
    model: ifcopenshell.file, 
    keywords: List[str], 
    case_sensitive: bool = False, 
    return_details: bool = True
) -> List[Union[str, Dict[str, Any]]]:
    """
    Scans all IfcPropertySet instances in the model and returns those matching 
    specific keywords in their names.

    Args:
        model (ifcopenshell.file): The loaded IFC model instance.
        keywords (List[str]): A list of strings to search for in PropertySet names 
            (e.g., ['thermal', 'energy', 'fire']).
        case_sensitive (bool): Whether the search should be case-sensitive. 
            Defaults to False.
        return_details (bool): If True, returns a list of dictionaries with 'Name' 
            and 'id'. If False, returns a list of matching names only. Defaults to True.

    Returns:
        List[Union[str, Dict[str, Any]]]: A list of matching property set names or 
            detailed dictionaries containing Name and id.

    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> # Find thermal property sets
        >>> thermal_sets = find_property_sets_by_keywords(model, ['thermal'])
        >>> # Find Revit property sets without IDs
        >>> revit_sets = find_property_sets_by_keywords(model, ['revit'], return_details=False)
    """
    if not keywords:
        return []

    results = []
    
    # Retrieve all property sets from the model
    all_psets = model.by_type('IfcPropertySet')

    for pset in all_psets:
        # Defensive attribute access for Name
        pset_name = getattr(pset, 'Name', None)
        
        # Skip if name is None or empty
        if not pset_name:
            continue

        # Prepare comparison strings based on case sensitivity
        target_name = pset_name if case_sensitive else pset_name.lower()
        
        matched = False
        for keyword in keywords:
            search_term = keyword if case_sensitive else keyword.lower()
            if search_term in target_name:
                matched = True
                break
        
        if matched:
            if return_details:
                # ID is a standard attribute, but accessed defensively if needed
                results.append({'Name': pset_name, 'id': pset.id()})
            else:
                results.append(pset_name)

    return results