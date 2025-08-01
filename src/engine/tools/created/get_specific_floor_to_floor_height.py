
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

def get_specific_floor_to_floor_height(ifc_file_path: str, from_storey_name: str, to_storey_name: str) -> Dict[str, Any]:
    """
    Calculate the floor-to-floor height between two specifically named building storeys.
    
    Args:
        ifc_file_path (str): Path to the IFC file
        from_storey_name (str): Name of the lower storey
        to_storey_name (str): Name of the upper storey
    
    Returns:
        Dict[str, Any]: Dictionary containing height information:
            - height: The vertical distance between the storeys (float)
            - from_storey: Name of the lower storey
            - to_storey: Name of the upper storey
            - from_elevation: Elevation of the lower storey (float)
            - to_elevation: Elevation of the upper storey (float)
            - unit: Unit of measurement (typically meters)
            - success: Boolean indicating if the operation was successful
            - message: Informative message about the result or any errors
    """
    try:
        # Load the IFC model
        model = ifcopenshell.open(ifc_file_path)
        
        # Get all building storeys
        storeys = model.by_type("IfcBuildingStorey")
        
        # Find the specified storeys by name
        from_storey = None
        to_storey = None
        
        for storey in storeys:
            if storey.Name == from_storey_name:
                from_storey = storey
            if storey.Name == to_storey_name:
                to_storey = storey
        
        # Check if both storeys were found
        if not from_storey:
            return {
                "height": 0.0,
                "from_storey": from_storey_name,
                "to_storey": to_storey_name,
                "from_elevation": 0.0,
                "to_elevation": 0.0,
                "unit": "meters",
                "success": False,
                "message": f"Storey '{from_storey_name}' not found in the model"
            }
        
        if not to_storey:
            return {
                "height": 0.0,
                "from_storey": from_storey_name,
                "to_storey": to_storey_name,
                "from_elevation": 0.0,
                "to_elevation": 0.0,
                "unit": "meters",
                "success": False,
                "message": f"Storey '{to_storey_name}' not found in the model"
            }
        
        # Get elevations
        from_elevation = getattr(from_storey, "Elevation", None)
        to_elevation = getattr(to_storey, "Elevation", None)
        
        # Check if elevations exist
        if from_elevation is None:
            return {
                "height": 0.0,
                "from_storey": from_storey_name,
                "to_storey": to_storey_name,
                "from_elevation": 0.0,
                "to_elevation": 0.0,
                "unit": "meters",
                "success": False,
                "message": f"No elevation data found for storey '{from_storey_name}'"
            }
        
        if to_elevation is None:
            return {
                "height": 0.0,
                "from_storey": from_storey_name,
                "to_storey": to_storey_name,
                "from_elevation": 0.0,
                "to_elevation": 0.0,
                "unit": "meters",
                "success": False,
                "message": f"No elevation data found for storey '{to_storey_name}'"
            }
        
        # Calculate height difference
        height = to_elevation - from_elevation
        
        # Check if the from_storey is actually below the to_storey
        if height < 0:
            return {
                "height": abs(height),
                "from_storey": from_storey_name,
                "to_storey": to_storey_name,
                "from_elevation": from_elevation,
                "to_elevation": to_elevation,
                "unit": "meters",
                "success": False,
                "message": f"Warning: '{from_storey_name}' is above '{to_storey_name}'. Negative height indicates reversed order."
            }
        
        # Return successful result
        return {
            "height": height,
            "from_storey": from_storey_name,
            "to_storey": to_storey_name,
            "from_elevation": from_elevation,
            "to_elevation": to_elevation,
            "unit": "meters",
            "success": True,
            "message": f"Successfully calculated floor-to-floor height between '{from_storey_name}' and '{to_storey_name}'"
        }
    
    except Exception as e:
        return {
            "height": 0.0,
            "from_storey": from_storey_name,
            "to_storey": to_storey_name,
            "from_elevation": 0.0,
            "to_elevation": 0.0,
            "unit": "meters",
            "success": False,
            "message": f"Error processing IFC file: {str(e)}"
        }
