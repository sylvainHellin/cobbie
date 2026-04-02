import ifcopenshell
import ifcopenshell.util.element
from typing import List


def check_504_2_riser_height(path_ifc_model: str) -> List[str]:
    """
    Check stair riser heights against building code requirements (504.2).
    
    Risers shall be 4 inches (100 mm) high minimum and 7 inches (180 mm) high maximum.
    
    This function checks for two types of violations:
    1. Riser height outside the acceptable range (100mm - 180mm)
    2. Non-uniform riser heights within the same stair
    
    Args:
        path_ifc_model: Path to the IFC model file.
        
    Returns:
        List[str]: List of IFC GUIDs of IfcStair elements that violate the rule.
        Returns an empty list if no violations are found or if the model contains no stairs.
        
    Example:
        >>> violations = check_504_2_riser_height('/path/to/model.ifc')
        >>> print(violations)  # ['3_3e8hPlTBFQmkqfJTZ0n3']
    """
    # Open the IFC model
    model = ifcopenshell.open(path_ifc_model)
    
    # Get all IfcStair elements
    stairs = model.by_type('IfcStair')
    
    # Define min and max riser heights in meters
    MIN_RISER_HEIGHT = 0.100  # 100 mm
    MAX_RISER_HEIGHT = 0.180  # 180 mm
    
    violations: List[str] = []
    skipped = 0
    
    for stair in stairs:
        try:
            # Collect riser heights from all sources for this stair
            riser_heights: List[float] = []
            
            # Get riser heights from Pset_StairCommon on the stair itself
            stair_pset = ifcopenshell.util.element.get_pset(stair, 'Pset_StairCommon')
            if stair_pset and 'RiserHeight' in stair_pset:
                riser_height = stair_pset['RiserHeight']
                if riser_height is not None and isinstance(riser_height, (int, float)):
                    riser_heights.append(riser_height)
            
            # Get riser heights from all IfcStairFlight elements decomposed by this stair
            for rel in stair.IsDecomposedBy:
                for related in rel.RelatedObjects:
                    if related.is_a() == 'IfcStairFlight':
                        flight_pset = ifcopenshell.util.element.get_pset(related, 'Pset_StairFlightCommon')
                        if flight_pset and 'RiserHeight' in flight_pset:
                            riser_height = flight_pset['RiserHeight']
                            if riser_height is not None and isinstance(riser_height, (int, float)):
                                riser_heights.append(riser_height)
            
            # Skip if no riser height data found
            if not riser_heights:
                skipped += 1
                continue
            
            # Check for violations:
            # 1. Any riser outside min/max range
            # 2. Non-uniform risers (multiple different heights within same stair)
            unique_heights = set(riser_heights)
            
            has_range_violation = False
            for height in riser_heights:
                if height < MIN_RISER_HEIGHT or height > MAX_RISER_HEIGHT:
                    violations.append(stair.GlobalId)
                    has_range_violation = True
                    break
            
            # Check for non-uniform risers if no range violation found
            if not has_range_violation and len(unique_heights) > 1:
                violations.append(stair.GlobalId)
                
        except (AttributeError, KeyError, RuntimeError) as e:
            skipped += 1
            continue
    
    if skipped > 0:
        print(f"Warning: Skipped {skipped} stair elements due to missing data or errors")
    
    return violations