
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

def get_all_storey_names(ifc_file_path: str) -> List[str]:
    """
    Retrieve all building storey names from an IFC model.
    
    This function extracts all IfcBuildingStorey elements from the IFC model 
    and returns their names. If a storey doesn't have a name, it uses the 
    GlobalId as fallback.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        
    Returns:
        List[str]: A list of building storey names from the IFC model. 
                  Returns an empty list if no storeys are found or if the 
                  model cannot be opened.
    """
    try:
        # Open the IFC file
        ifc_file = ifcopenshell.open(ifc_file_path)
        
        # Get all IfcBuildingStorey entities
        storeys = ifc_file.by_type("IfcBuildingStorey")
        
        # Extract names, using GlobalId as fallback
        storey_names = []
        for storey in storeys:
            name = getattr(storey, 'Name', None)
            if name is None or name == '':
                # Use GlobalId as fallback if Name is not available
                name = getattr(storey, 'GlobalId', 'Unknown')
            storey_names.append(name)
        
        return storey_names
        
    except Exception as e:
        # Return empty list if model cannot be opened or any other error occurs
        return []
