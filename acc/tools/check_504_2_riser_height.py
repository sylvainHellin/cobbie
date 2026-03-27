import ifcopenshell
import ifcopenshell.util.element
from typing import List

def check_504_2_riser_height(path_ifc_model: str) -> List[str]:
    """
    Check stair riser heights against ADA rule 504.2.
    
    Rule 504.2 requires risers to be between 100mm (0.1m) minimum and 180mm (0.18m) maximum.
    
    This function examines all IfcStair entities in the IFC model and checks their
    associated riser heights from property sets (Psets). The riser height can be
    stored in Pset_StairCommon on the stair itself, or in Pset_StairFlightCommon
    on associated IfcStairFlight entities.
    
    Args:
        path_ifc_model (str): Path to the IFC model file.
    
    Returns:
        List[str]: A sorted list of IFC GUIDs of stairs that violate the riser height rule.
                  Returns empty list if no violations found or if no stair data is available.
    
    Example:
        >>> violations = check_504_2_riser_height('/path/to/model.ifc')
        >>> print(violations)
        ['0wkEuT1wr1kOyafLY4v_O1', '21ldoMpbP4VfsJ0XGY_34d']
    """
    model = ifcopenshell.open(path_ifc_model)
    
    min_height = 0.1  # 100 mm minimum in meters
    max_height = 0.18  # 180 mm maximum in meters
    
    violations = set()
    no_data_count = 0
    
    # Get all IfcStair entities
    stairs = model.by_type('IfcStair')
    
    if not stairs:
        return []
    
    for stair in stairs:
        riser_height = None
        
        # Method 1: Check Pset_StairCommon on the stair itself
        try:
            pset = ifcopenshell.util.element.get_pset(stair, 'Pset_StairCommon')
            if pset and 'RiserHeight' in pset:
                riser_height = pset['RiserHeight']
        except (AttributeError, KeyError):
            pass
        
        # Method 2: Check Pset_StairFlightCommon on the stair itself
        # (sometimes properties are defined on stair rather than flights)
        if riser_height is None:
            try:
                pset = ifcopenshell.util.element.get_pset(stair, 'Pset_StairFlightCommon')
                if pset and 'RiserHeight' in pset:
                    riser_height = pset['RiserHeight']
            except (AttributeError, KeyError):
                pass
        
        # Method 3: Check associated IfcStairFlight entities
        if riser_height is None:
            if hasattr(stair, 'IsDecomposedBy'):
                for rel in stair.IsDecomposedBy:
                    for related in rel.RelatedObjects:
                        if related.is_a('IfcStairFlight'):
                            try:
                                pset = ifcopenshell.util.element.get_pset(related, 'Pset_StairFlightCommon')
                                if pset and 'RiserHeight' in pset:
                                    riser_height = pset['RiserHeight']
                                    break
                            except (AttributeError, KeyError):
                                pass
                            if riser_height is not None:
                                break
        
        # Check if riser height violates the rule
        if riser_height is not None:
            if riser_height < min_height or riser_height > max_height:
                violations.add(stair.GlobalId)
        else:
            no_data_count += 1
    
    if no_data_count > 0:
        print(f"Warning: Could not find riser height data for {no_data_count} stair(s)")
    
    return sorted(list(violations))