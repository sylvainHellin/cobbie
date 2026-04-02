import ifcopenshell
import ifcopenshell.util.element
from typing import List


def check_504_2_tread_length(path_ifc_model: str) -> List[str]:
    """
    Check stair tread lengths against the minimum requirement of 280mm (0.28m).
    
    Rule 504.2: Treads and Risers - Treads shall be 11 inches (280 mm) deep minimum.
    
    Args:
        path_ifc_model: Path to the IFC model file.
        
    Returns:
        List of IFC GUIDs of all stair elements that violate the rule (have
        tread length less than 0.28m). Returns empty list if no violations found
        or if tread length data is unavailable.
        
    Example:
        >>> violations = check_504_2_tread_length('/path/to/model.ifc')
        >>> print(f"Found {len(violations)} violations")
    """
    model = ifcopenshell.open(path_ifc_model)
    violations = []
    MIN_TREAD_LENGTH = 0.28  # 280mm in meters
    
    # Find all stair elements in the model
    stairs = model.by_type('IfcStair')
    
    if not stairs:
        return []
    
    for stair in stairs:
        try:
            # Get all property sets for the stair element
            psets = ifcopenshell.util.element.get_psets(stair)
            
            tread_length = None
            
            # Check standard IFC property set first
            if 'Pset_StairCommon' in psets:
                tread_length = psets['Pset_StairCommon'].get('TreadLength')
            
            # If tread length is found and is a valid number, check against minimum
            if tread_length is not None and isinstance(tread_length, (int, float)):
                if tread_length < MIN_TREAD_LENGTH:
                    violations.append(stair.GlobalId)
                    
        except (AttributeError, KeyError, RuntimeError) as e:
            # Skip elements with property access issues but continue processing others
            continue
    
    return violations