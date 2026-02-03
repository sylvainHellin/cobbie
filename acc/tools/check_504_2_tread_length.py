import ifcopenshell
import ifcopenshell.util.element
from typing import List


def check_504_2_tread_length(path_ifc_model: str) -> List[str]:
    """
    Check stair tread lengths against the minimum 280mm requirement.

    Rule 504.2: Treads and Risers - Treads shall be 11 inches (280 mm) deep minimum.

    Args:
        path_ifc_model: Path to the IFC model file.

    Returns:
        List of IFC GUIDs of stairs that violate the rule (tread length < 280mm).
        Returns empty list if no violations are found or model has no stairs.

    Example:
        >>> violations = check_504_2_tread_length('/path/to/model.ifc')
        >>> print(violations)
        ['0wkEuT1wr1kOyafLY4v_O1', '21ldoMpbP4VfsJ0XGY_34d']
    """
    model = ifcopenshell.open(path_ifc_model)
    violations = []
    
    # Get all stair elements
    stairs = model.by_type('IfcStair')
    
    if not stairs:
        return []
    
    for stair in stairs:
        try:
            # Get property sets for the stair
            psets = ifcopenshell.util.element.get_psets(stair)
            
            # Extract tread length from Pset_StairCommon
            tread_length = psets.get('Pset_StairCommon', {}).get('TreadLength')
            
            # Check if tread length is defined and below minimum
            if tread_length is not None and tread_length < 0.28:
                violations.append(stair.GlobalId)
                
        except (AttributeError, KeyError, RuntimeError) as e:
            # Skip elements with data access issues
            continue
    
    return violations