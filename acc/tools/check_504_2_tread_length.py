import ifcopenshell
import ifcopenshell.util.element
from typing import List


def check_504_2_tread_length(path_ifc_model: str) -> List[str]:
    """
    Check stair tread lengths against minimum requirement (280 mm).
    
    Rule 504.2: Treads shall be 11 inches (280 mm) deep minimum.
    
    This function analyzes all IfcStair elements in the IFC model and returns
    the GUIDs of stairs that violate the minimum tread length requirement.
    
    Args:
        path_ifc_model: Path to the IFC model file
        
    Returns:
        List of IFC GUIDs (strings) for stairs that violate the rule.
        Returns empty list if no violations found or if tread length data is unavailable.
        
    Note:
        - Tread length is read from Pset_StairCommon.TreadLength property set
        - Missing tread length data results in the stair being skipped (not counted as violation)
        - Units are expected in meters (280 mm = 0.28 m)
        
    Example:
        >>> violations = check_504_2_tread_length('/path/to/model.ifc')
        >>> print(f"Found {len(violations)} stairs with insufficient tread length")
    """
    model = ifcopenshell.open(path_ifc_model)
    min_tread_length = 0.28  # 280 mm in meters
    violations = []
    skipped = 0
    
    # Get all stair elements
    stairs = model.by_type('IfcStair')
    
    if not stairs:
        return []
    
    for stair in stairs:
        try:
            # Get all property sets for the stair
            psets = ifcopenshell.util.element.get_psets(stair)
            
            # Try to get TreadLength from Pset_StairCommon
            tread_length = None
            if 'Pset_StairCommon' in psets:
                tread_length = psets['Pset_StairCommon'].get('TreadLength')
            
            # Skip if tread length is not found
            if tread_length is None:
                skipped += 1
                continue
            
            # Check if tread length is less than minimum
            if tread_length < min_tread_length:
                violations.append(stair.GlobalId)
                
        except (AttributeError, KeyError, RuntimeError) as e:
            # Handle specific exceptions when accessing properties
            skipped += 1
            continue
    
    if skipped > 0:
        print(f"Warning: Skipped {skipped}/{len(stairs)} stair elements due to missing tread length data")
    
    return violations