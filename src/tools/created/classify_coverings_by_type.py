import ifcopenshell
from typing import List, Dict, Optional


def classify_coverings_by_type(
    coverings: List[ifcopenshell.entity_instance]
) -> Dict[str, List[ifcopenshell.entity_instance]]:
    """
    Classifies a list of IfcCovering elements into categories (Wall, Ceiling, Floor, Other).
    
    Uses a two-step logic:
    1. Checks the 'PredefinedType' attribute of each element
    2. If the type is 'NOTDEFINED', attempts to infer the category by searching
       for keywords ('wall', 'ceiling', 'floor') in the element's Name
    
    This helps standardize the analysis of IFC models where covering types are
    defined via naming conventions when explicit types are not used.
    
    Args:
        coverings: List of IfcCovering objects to classify.
    
    Returns:
        A dictionary with keys 'WALL', 'CEILING', 'FLOOR', and 'OTHER' mapping to
        lists of classified IfcCovering elements.
    
    Example:
        >>> model = ifcopenshell.open('model.ifc')
        >>> coverings = model.by_type('IfcCovering')
        >>> classified = classify_coverings_by_type(coverings)
        >>> print(f"Wall coverings: {len(classified['WALL'])}")
        >>> print(f"Ceiling coverings: {len(classified['CEILING'])}")
    """
    # Input validation
    if not coverings:
        return {'WALL': [], 'CEILING': [], 'FLOOR': [], 'OTHER': []}
    
    # Initialize result dictionary with empty lists
    result: Dict[str, List[ifcopenshell.entity_instance]] = {
        'WALL': [],
        'CEILING': [],
        'FLOOR': [],
        'OTHER': []
    }
    
    skipped = 0
    
    for covering in coverings:
        try:
            # Step 1: Check PredefinedType attribute
            predefined_type = getattr(covering, 'PredefinedType', 'NOTDEFINED')
            
            category = 'OTHER'
            
            if predefined_type == 'WALL':
                category = 'WALL'
            elif predefined_type == 'CEILING':
                category = 'CEILING'
            elif predefined_type == 'FLOOR':
                category = 'FLOOR'
            elif predefined_type == 'NOTDEFINED':
                # Step 2: Infer from Name if PredefinedType is NOTDEFINED
                name = getattr(covering, 'Name', '')
                if name:
                    name_lower = name.lower()
                    if 'wall' in name_lower:
                        category = 'WALL'
                    elif 'ceiling' in name_lower:
                        category = 'CEILING'
                    elif 'floor' in name_lower or 'vloer' in name_lower:
                        category = 'FLOOR'
                else:
                    # No name to infer from, keep as OTHER
                    category = 'OTHER'
            
            result[category].append(covering)
            
        except AttributeError:
            # Skip elements that don't have expected attributes
            skipped += 1
            continue
    
    if skipped > 0:
        print(f"Warning: Skipped {skipped} elements due to missing attributes")
    
    return result