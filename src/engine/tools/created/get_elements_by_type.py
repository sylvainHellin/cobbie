import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.util.placement
import ifcopenshell.util.geolocation
import ifcopenshell.util.system
import ifcopenshell.geom
from typing import List


def get_elements_by_type(
    ifc_file_path: str, ifc_type: str
) -> List[ifcopenshell.entity_instance]:
    """
    Retrieves elements of a specified IFC type from an IFC model.

    Args:
        ifc_file_path (str): The path to the IFC file.
        ifc_type (str): The IFC entity type to retrieve (e.g., 'IfcWall', 'IfcBeam', 'IfcDoor').

    Returns:
        List[ifcopenshell.entity_instance]: A list of IfcOpenShell entity instances
                                            of the specified type. Each entity has
                                            accessible attributes like 'Name' and 'GlobalId'.
                                            Returns an empty list if the file cannot be opened
                                            or no elements of the specified type are found.
    """
    try:
        ifc_file = ifcopenshell.open(ifc_file_path)
        elements = ifc_file.by_type(ifc_type)
        return elements
    except Exception as e:
        print(f"Error opening IFC file or retrieving elements: {e}")
        return []
