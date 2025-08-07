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

def calculate_usable_floor_area(ifc_file_path: str) -> float:
    """
    Calculate the Usable Floor Area (UFA) from IfcSpace elements in an IFC model.
    
    This function extracts area properties from IfcSpace elements and sums them to
    determine the total usable floor area. It handles different property set
    conventions across various BIM authoring software.
    
    The function looks for area information in the following property sets (in order of preference):
    1. PSet_Revit_Dimensions.Area (for Revit-exported IFC models)
    2. GSA Space Areas.GSA BIM Area (for models following GSA standards)
    3. BaseQuantities.Area (from quantity sets)
    
    Args:
        ifc_file_path (str): Path to the IFC file
        
    Returns:
        float: Total usable floor area in square meters (or the units used in the IFC model)
        
    Assumptions:
        - The IFC model contains IfcSpace elements with area properties in recognized property sets
        - Area values are in consistent units (typically square meters)
        - If multiple area properties exist for a space, the first available one is used
        - PSet_Revit_Dimensions is specific to IFC models exported from Revit
        
    Example:
        >>> ufa = calculate_usable_floor_area("path/to/model.ifc")
        >>> print(f"Usable Floor Area: {ufa:.2f} m²")
    """
    # Open the IFC file
    model = ifcopenshell.open(ifc_file_path)
    
    # Get all IfcSpace elements
    spaces = model.by_type("IfcSpace")
    
    total_ufa = 0.0
    
    # Define the priority order for property sets and properties
    area_property_priorities = [
        ("PSet_Revit_Dimensions", "Area"),
        ("GSA Space Areas", "GSA BIM Area"),
        ("BaseQuantities", "Area")
    ]
    
    for space in spaces:
        # Get all property sets for this space
        psets = ifcopenshell.util.element.get_psets(space)
        
        # Try to find area in the priority order
        area_found = False
        for pset_name, prop_name in area_property_priorities:
            if pset_name in psets and prop_name in psets[pset_name]:
                area_value = psets[pset_name][prop_name]
                if isinstance(area_value, (int, float)):
                    total_ufa += area_value
                    area_found = True
                    break
        
        # If no area property was found in priority sets, check any pset for an "Area" property
        if not area_found:
            for pset_name, pset_data in psets.items():
                if isinstance(pset_data, dict) and "Area" in pset_data:
                    area_value = pset_data["Area"]
                    if isinstance(area_value, (int, float)):
                        total_ufa += area_value
                        area_found = True
                        break
    
    return total_ufa