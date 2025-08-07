
import ifcopenshell
import ifcopenshell.util.element
from typing import List

def get_exterior_elements(ifc_file_path: str, ifc_type: str) -> List[ifcopenshell.entity_instance]:
    """
    Retrieves elements of a specified IFC type that are classified as exterior elements,
    based on properties like 'IsExternal' in property sets such as 'Pset_WallCommon', 
    'Pset_SlabCommon', etc.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        ifc_type (str): The IFC entity type to retrieve (e.g., 'IfcWall', 'IfcSlab')
        
    Returns:
        List[ifcopenshell.entity_instance]: A list of IfcOpenShell entity instances of 
        the specified type that are classified as exterior elements
        
    Note:
        This function assumes the IFC model follows standard property set conventions
        where exterior elements have an 'IsExternal' property set to True in property
        sets like 'Pset_WallCommon', 'Pset_SlabCommon', etc.
        
        For IFC models exported from specific BIM authoring software like Revit,
        property sets may follow naming conventions such as 'PSet_Revit_*' in addition
        to standard property sets.
    """
    # Load the IFC file
    ifc_file = ifcopenshell.open(ifc_file_path)
    
    # Get all elements of the specified type
    elements = ifc_file.by_type(ifc_type)
    
    # Filter for exterior elements
    exterior_elements = []
    
    # Common property sets that might contain IsExternal property
    common_psets = [
        "Pset_WallCommon",
        "Pset_SlabCommon", 
        "Pset_DoorCommon",
        "Pset_WindowCommon",
        "Pset_CoveringCommon"
    ]
    
    for element in elements:
        # Get all property sets for this element
        psets = ifcopenshell.util.element.get_psets(element)
        
        # Check if any of the common property sets has IsExternal=True
        is_exterior = False
        for pset_name in common_psets:
            if pset_name in psets and 'IsExternal' in psets[pset_name]:
                if psets[pset_name]['IsExternal'] == True:
                    is_exterior = True
                    break
        
        # If no common property set found, check all property sets
        if not is_exterior:
            for pset_name, properties in psets.items():
                if 'IsExternal' in properties and properties['IsExternal'] == True:
                    is_exterior = True
                    break
        
        if is_exterior:
            exterior_elements.append(element)
    
    return exterior_elements
