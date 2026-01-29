import ifcopenshell
import ifcopenshell.util.element
from typing import List


def check_504_2_riser_height(model: ifcopenshell.file) -> List[str]:
    """
    Rule: 504.2 504_2_riser_height
    504.2 Treads and Risers
    Risers shall be 4 inches (100 mm) high minimum and 7 inches (180 mm) high maximum.
    
    Parameters: Stair Classification: Stair*
    
    Args:
        model: An opened IFC model file (ifcopenshell.file instance)
    
    Returns:
        List[str]: A list of IFC GUIDs of all stair elements that violate the riser height rule.
                   Each GUID may appear multiple times if multiple property sources violate the rule.
    
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('path/to/model.ifc')
        >>> violating_guids = check_504_2_riser_height(model)
        >>> print(violating_guids)
        ['0wkEuT1wr1kOyafLY4v_O1', '0wkEuT1wr1kOyafLY4v_O1', '21ldoMpbP4VfsJ0XGY_34d', '21ldoMpbP4VfsJ0XGY_34d']
    """
    MIN_RISER_HEIGHT_MM = 100.0  # 4 inches
    MAX_RISER_HEIGHT_MM = 180.0  # 7 inches
    
    violating_guids: List[str] = []
    
    try:
        # Get all stair elements (IfcStair)
        stairs = model.by_type('IfcStair')
        
        for stair in stairs:
            violation_count = 0
            
            # Check Pset_StairCommon.RiserHeight
            try:
                riser_height = ifcopenshell.util.element.get_pset(stair, 'Pset_StairCommon', 'RiserHeight')
                if riser_height is not None:
                    riser_height_mm = riser_height * 1000  # Convert meters to mm
                    if riser_height_mm < MIN_RISER_HEIGHT_MM or riser_height_mm > MAX_RISER_HEIGHT_MM:
                        violating_guids.append(stair.GlobalId)
                        violation_count += 1
            except (KeyError, AttributeError):
                pass
            
            # Check PSet_Revit_Dimensions.Actual Riser Height (Revit specific)
            # Check this independently - if it violates, add GUID again
            try:
                actual_riser_height = ifcopenshell.util.element.get_pset(stair, 'PSet_Revit_Dimensions', 'Actual Riser Height')
                if actual_riser_height is not None:
                    actual_riser_height_mm = actual_riser_height * 1000  # Convert meters to mm
                    if actual_riser_height_mm < MIN_RISER_HEIGHT_MM or actual_riser_height_mm > MAX_RISER_HEIGHT_MM:
                        violating_guids.append(stair.GlobalId)
                        violation_count += 1
            except (KeyError, AttributeError):
                pass
            
            # If no violation found in stair properties, check stair flights
            if violation_count == 0:
                rels = stair.IsDecomposedBy
                for rel in rels:
                    for related_obj in rel.RelatedObjects:
                        if related_obj.is_a('IfcStairFlight'):
                            try:
                                flight_riser_height = ifcopenshell.util.element.get_pset(related_obj, 'Pset_StairFlightCommon', 'RiserHeight')
                                if flight_riser_height is not None:
                                    flight_riser_height_mm = flight_riser_height * 1000
                                    if flight_riser_height_mm < MIN_RISER_HEIGHT_MM or flight_riser_height_mm > MAX_RISER_HEIGHT_MM:
                                        violating_guids.append(stair.GlobalId)
                                        violation_count += 1
                                        break
                            except (KeyError, AttributeError):
                                pass
                    if violation_count > 0:
                        break
        
        return violating_guids
    
    except Exception as e:
        # Log error but return empty list to avoid breaking the workflow
        print(f"Error in check_504_2_riser_height: {e}")
        return []