import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.util.placement
import ifcopenshell.util.geolocation
import ifcopenshell.util.system
import ifcopenshell.geom
import math
import json
from typing import Dict, Any

def estimate_room_flooring_requirements(model_path: str) -> Dict[str, Dict[str, float]]:
    """
    Estimate room-by-room flooring requirements from an IFC model.
    
    This function extracts area information for all rooms/spaces in an IFC model
    and groups them by level and room type. The areas are estimates based on 
    property set information and should not be considered exact values.
    
    Args:
        model_path (str): Path to the IFC model file
        
    Returns:
        Dict[str, Dict[str, float]]: A dictionary with levels as keys, each containing
        a dictionary of room types and their estimated total floor areas.
        
    Note:
        - This function works with property sets like "GSA Space Areas" or 
          "PSet_Revit_Dimensions" for area extraction
        - Room types are determined by the first letter of the space name
        - Areas are estimates and may not represent actual flooring requirements
        - Results should be used for planning purposes only
    """
    # Load the IFC model
    model = ifcopenshell.open(model_path)
    
    # Find all IfcSpace entities
    spaces = model.by_type("IfcSpace")
    
    # Initialize results dictionary
    results = {}
    
    # Process each space
    for space in spaces:
        # Get space name
        space_name = space.Name if space.Name else "Unknown"
        
        # Extract level information from property sets
        psets = ifcopenshell.util.element.get_psets(space)
        level = "Unknown Level"
        for pset_name, pset_data in psets.items():
            if 'Level' in pset_data:
                level = pset_data['Level']
                break
        
        # Extract area information
        area = 0.0
        # Try to get area from GSA Space Areas first
        if 'GSA Space Areas' in psets and 'GSA BIM Area' in psets['GSA Space Areas']:
            area = psets['GSA Space Areas']['GSA BIM Area']
        # Fallback to PSet_Revit_Dimensions
        elif 'PSet_Revit_Dimensions' in psets and 'Area' in psets['PSet_Revit_Dimensions']:
            area = psets['PSet_Revit_Dimensions']['Area']
        
        # Determine room type from the first letter of the space name
        room_type = space_name[0] if space_name and len(space_name) > 0 else "Unknown"
        
        # Initialize level in results if not present
        if level not in results:
            results[level] = {}
        
        # Add area to the appropriate room type
        if room_type not in results[level]:
            results[level][room_type] = 0.0
        
        results[level][room_type] += area
    
    # Add disclaimer to the results
    disclaimer = "Note: These are estimated values based on property set information from the IFC model. They may not represent exact flooring requirements and should be used for planning purposes only."
    
    # Return results with disclaimer
    return results