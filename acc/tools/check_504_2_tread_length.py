import ifcopenshell
import ifcopenshell.util.element
from typing import List


def check_504_2_tread_length(model: ifcopenshell.file) -> List[str]:
    """
    Check stair elements for tread length violations.
    
    Rule: 504.2 Treads and Risers
    Treads shall be 11 inches (280 mm) deep minimum.
    
    Parameters: Stair Classification: Stair*
    
    Args:
        model: An opened IfcOpenShell file object
        
    Returns:
        List[str]: A list of IFC GUIDs of all stair elements that violate
                   the minimum tread length requirement (less than 280mm)
                   
    Example:
        >>> import ifcopenshell
        >>> model = ifcopenshell.open('model.ifc')
        >>> violations = check_504_2_tread_length(model)
        >>> print(violations)
        ['0wkEuT1wr1kOyafLY4v_O1', '21ldoMpbP4VfsJ0XGY_34d']
    """
    violating_guids: List[str] = []
    minimum_tread_length_mm = 280.0  # 11 inches in mm
    minimum_tread_length_m = minimum_tread_length_mm / 1000.0  # Convert to meters
    
    try:
        # Check IfcStair elements as specified by 'Stair*' classification
        elements = model.by_type('IfcStair')
        
        for element in elements:
            try:
                # Get all property sets for the element
                psets = ifcopenshell.util.element.get_psets(element)
                
                # Look for TreadLength in any property set
                tread_length = None
                for pset_name, pset_data in psets.items():
                    if 'TreadLength' in pset_data:
                        tread_length = pset_data['TreadLength']
                        break
                
                # If tread length is found and violates the requirement
                if tread_length is not None:
                    if tread_length < minimum_tread_length_m:
                        violating_guids.append(element.GlobalId)
                        
            except Exception:
                # Skip element if there's an error processing it
                continue
                
    except Exception:
        # Return empty list if there's a major error
        return []
    
    return violating_guids