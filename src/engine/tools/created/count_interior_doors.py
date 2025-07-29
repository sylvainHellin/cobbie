import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.util.placement
import ifcopenshell.util.geolocation
import ifcopenshell.util.system
import ifcopenshell.geom
import math
import json
from typing import *


def count_interior_doors(ifc_file_path: str) -> int:
    """
    Count the number of interior doors in an IFC model.
    
    This function identifies interior doors by checking the Pset_DoorCommon property set
    and looking for the IsExternal property. If IsExternal is False, the door is considered
    an interior door.
    
    This approach works well with IFC models exported from Revit, which typically include
    the Pset_DoorCommon property set with the IsExternal property.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        
    Returns:
        int: Number of interior doors in the model
    """
    # Load the IFC model
    model = ifcopenshell.open(ifc_file_path)
    
    # Get all door entities
    doors = model.by_type("IfcDoor")
    
    interior_count = 0
    
    # Iterate through all doors
    for door in doors:
        # Get all property sets for the door
        psets = ifcopenshell.util.element.get_psets(door)
        
        # Check if Pset_DoorCommon exists and has IsExternal property
        if 'Pset_DoorCommon' in psets:
            pset_door_common = psets['Pset_DoorCommon']
            # Check if IsExternal property exists and is False
            if 'IsExternal' in pset_door_common and pset_door_common['IsExternal'] == False:
                interior_count += 1
    
    return interior_count