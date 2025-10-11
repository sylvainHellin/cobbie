import ifcopenshell
import ifcopenshell.util.element
from typing import List, Dict, Optional


def get_room_names_and_functions(model_path: str, room_codes: List[str] = None) -> Dict[str, str]:
    """
    Extract functional room names from an IFC model by analyzing IfcSpace entities.
    
    This function searches for IfcSpace entities and extracts their functional names
    from various property sets and attributes, with a specific priority order.
    
    Args:
        model_path: Path to the IFC model file
        room_codes: Optional list of specific room codes to analyze (if None, analyzes all rooms)
    
    Returns:
        Dictionary mapping room codes to their functional names
    
    Note:
        This function is designed to work with IFC models exported from Revit.
        It looks for functional names in the following priority order:
        1. PSet_Revit_Identity Data -> Name property
        2. LongName attribute of IfcSpace
        3. PSet_Revit_Other -> Category Description property
        
        The room code is extracted from the Name attribute of the IfcSpace entity.
    """
    # Open the IFC model
    model = ifcopenshell.open(model_path)
    
    # Get all IfcSpace entities
    spaces = model.by_type('IfcSpace')
    
    room_mapping = {}
    
    for space in spaces:
        # Extract room code from Name attribute
        room_code = space.Name
        
        # Skip if room_codes is specified and this room is not in the list
        if room_codes is not None and room_code not in room_codes:
            continue
        
        # Skip if no room code
        if not room_code:
            continue
        
        functional_name = None
        
        # Priority 1: Look for Name in PSet_Revit_Identity Data
        psets = ifcopenshell.util.element.get_psets(space)
        if 'PSet_Revit_Identity Data' in psets:
            identity_data = psets['PSet_Revit_Identity Data']
            if 'Name' in identity_data and identity_data['Name']:
                functional_name = identity_data['Name']
        
        # Priority 2: Use LongName attribute if not found in identity data
        if not functional_name and space.LongName:
            functional_name = space.LongName
        
        # Priority 3: Look for Category Description in PSet_Revit_Other
        if not functional_name and 'PSet_Revit_Other' in psets:
            other_data = psets['PSet_Revit_Other']
            if 'Category Description' in other_data and other_data['Category Description']:
                functional_name = other_data['Category Description']
        
        # If still no functional name, use the room code as fallback
        if not functional_name:
            functional_name = room_code
        
        room_mapping[room_code] = functional_name
    
    return room_mapping