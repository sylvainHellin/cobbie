import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.util.placement
import ifcopenshell.util.geolocation
import ifcopenshell.util.system
import ifcopenshell.geom
from typing import *


def get_interior_doors_count(ifc_file_path: str) -> int:
    """
    Retrieve all IfcDoor entities from the specified IFC model and return the count of doors
    identified as interior. A door is considered interior if its Pset_DoorCommon property set
    has IsExternal set to False.

    Args:
        ifc_file_path (str): Path to the IFC file

    Returns:
        int: Count of interior doors (doors with Pset_DoorCommon.IsExternal = False)
    """
    # Open the IFC file
    model = ifcopenshell.open(ifc_file_path)

    # Get all IfcDoor entities
    doors = model.by_type("IfcDoor")

    # Counter for interior doors
    interior_doors_count = 0

    # Iterate through all doors
    for door in doors:
        # Get all property sets for the door
        psets = ifcopenshell.util.element.get_psets(door)

        # Check if Pset_DoorCommon exists
        if "Pset_DoorCommon" in psets:
            # Check if IsExternal property exists and is False
            if "IsExternal" in psets["Pset_DoorCommon"]:
                if psets["Pset_DoorCommon"]["IsExternal"] == False:
                    interior_doors_count += 1

    return interior_doors_count
