
import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.util.placement
import ifcopenshell.util.geolocation
import ifcopenshell.geom
import math
import json
from typing import *

def get_all_storey_names_comprehensive(
    ifc_file_path: str,
    include_elevations: bool = False,
    include_guids: bool = False,
    sort_by_elevation: bool = False
) -> Union[List[str], List[Dict[str, Any]]]:
    """
    Retrieve all building storey names from an IFC model with additional comprehensive information.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        include_elevations (bool, optional): Whether to include elevation information for each storey (default: False)
        include_guids (bool, optional): Whether to include GlobalIds for each storey (default: False)
        sort_by_elevation (bool, optional): Whether to sort results by elevation (default: False)
        
    Returns:
        When basic mode (no additional parameters): List[str] - A list of building storey names
        When comprehensive mode (with additional parameters): List[Dict[str, Any]] - A list of dictionaries containing:
            - "name": Storey name
            - "elevation": Elevation value (if include_elevations=True)
            - "guid": GlobalId (if include_guids=True)
            - "order": Position in sorted order (if sort_by_elevation=True)
            
    Note:
        This function follows the same pattern as get_floor_to_floor_heights vs get_floor_to_floor_heights_comprehensive,
        providing both basic and enhanced versions of storey information retrieval.
    """
    try:
        # Open the IFC file
        ifc_file = ifcopenshell.open(ifc_file_path)
        
        # Get all building storey entities
        storeys = ifc_file.by_type("IfcBuildingStorey")
        
        # If no storeys found, return empty list
        if not storeys:
            return []
        
        # Basic mode - return list of storey names only
        if not (include_elevations or include_guids or sort_by_elevation):
            return [storey.Name for storey in storeys if storey.Name]
        
        # Comprehensive mode - build list of dictionaries
        result = []
        
        for storey in storeys:
            storey_info = {"name": storey.Name or ""}
            
            if include_guids:
                storey_info["guid"] = storey.GlobalId
            
            if include_elevations:
                try:
                    elevation = ifcopenshell.util.placement.get_storey_elevation(storey)
                    storey_info["elevation"] = elevation
                except:
                    storey_info["elevation"] = None
            
            result.append(storey_info)
        
        # Sort by elevation if requested
        if sort_by_elevation:
            # Sort by elevation, handling None values
            result.sort(key=lambda x: x.get("elevation") or 0)
            
            # Add order information
            for i, storey_info in enumerate(result):
                storey_info["order"] = i
        
        return result
        
    except Exception as e:
        # Return empty list if model cannot be opened or any other error occurs
        return []
