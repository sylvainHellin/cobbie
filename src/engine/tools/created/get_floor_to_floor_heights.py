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


def get_floor_to_floor_heights(ifc_file_path: str) -> List[Dict[str, Any]]:
    """
    Calculate floor-to-floor heights between consecutive building storeys in an IFC model.
    
    Parameters:
    - ifc_file_path (str): Path to the IFC file
    
    Returns:
    - List[Dict[str, Any]]: A list of dictionaries containing floor-to-floor height information.
      Each dictionary includes:
      - "from_storey": Name of the lower storey
      - "to_storey": Name of the upper storey
      - "height": Vertical distance between the storeys (float)
      - "from_elevation": Elevation of the lower storey (float)
      - "to_elevation": Elevation of the upper storey (float)
      - "unit": Unit of measurement (typically meters)
    """
    # Open the IFC file
    model = ifcopenshell.open(ifc_file_path)
    
    # Get all IfcBuildingStorey entities
    storeys = model.by_type("IfcBuildingStorey")
    
    # Extract storey information with elevations
    storey_data = []
    for storey in storeys:
        name = storey.Name if storey.Name else "Unnamed Storey"
        elevation = getattr(storey, 'Elevation', None)
        
        # Skip storeys without elevation data
        if elevation is not None:
            storey_data.append({
                'name': name,
                'elevation': elevation
            })
    
    # Sort storeys by elevation
    storey_data.sort(key=lambda x: x['elevation'])
    
    # Calculate floor-to-floor heights
    results = []
    for i in range(len(storey_data) - 1):
        from_storey = storey_data[i]
        to_storey = storey_data[i + 1]
        
        height = to_storey['elevation'] - from_storey['elevation']
        
        results.append({
            "from_storey": from_storey['name'],
            "to_storey": to_storey['name'],
            "height": height,
            "from_elevation": from_storey['elevation'],
            "to_elevation": to_storey['elevation'],
            "unit": "meters"
        })
    
    return results