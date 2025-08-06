import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.util.placement
import ifcopenshell.util.geolocation
import ifcopenshell.util.system
import ifcopenshell.geom
import math
import json
from typing import List

def get_all_room_names(ifc_file_path: str) -> List[str]:
    """
    Retrieves the names of all rooms/spaces in an IFC model.
    
    This function extracts all IfcSpace elements from the IFC model and returns
    their names. If a space doesn't have a name, it will use the GlobalId as fallback.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        
    Returns:
        List[str]: A list of room/space names from the IFC model.
                  Returns an empty list if no spaces are found or if the model cannot be opened.
                  
    Note:
        This function assumes the IFC model follows standard IFC schema where
        spaces are represented as IfcSpace entities with Name attributes.
    """
    try:
        # Open the IFC file
        ifc_file = ifcopenshell.open(ifc_file_path)
    except Exception as e:
        # Return empty list if file cannot be opened
        return []
    
    try:
        # Get all IfcSpace elements
        spaces = ifc_file.by_type("IfcSpace")
        
        # Extract names from spaces
        space_names = []
        for space in spaces:
            # Use Name attribute if available, otherwise fallback to GlobalId
            name = getattr(space, "Name", None)
            if name is None:
                # Fallback to GlobalId if Name is not available
                name = getattr(space, "GlobalId", "Unnamed Space")
            space_names.append(name)
        
        return space_names
    except Exception as e:
        # Return empty list if any error occurs during processing
        return []