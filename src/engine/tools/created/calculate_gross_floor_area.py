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


def calculate_gross_floor_area(ifc_model_path: str) -> float:
    """
    Calculate the total gross floor area from an IFC model by summing up all space areas.
    
    This function handles different property set naming conventions for area values:
    - Prioritizes "GSA BIM Area" from "GSA Space Areas" property set
    - Falls back to "Area" from "PSet_Revit_Dimensions" property set
    
    Args:
        ifc_model_path (str): Path to the IFC model file
        
    Returns:
        float: Total gross floor area in square units
        
    Note:
        This function assumes the IFC model contains IfcSpace entities with area properties
        in either "GSA Space Areas" or "PSet_Revit_Dimensions" property sets.
    """
    # Load the IFC model
    ifc_model = ifcopenshell.open(ifc_model_path)
    
    # Get all IfcSpace entities
    spaces = ifc_model.by_type("IfcSpace")
    
    total_area = 0.0
    
    # Process each space
    for space in spaces:
        # Get all property sets for this space
        psets = ifcopenshell.util.element.get_psets(space)
        
        area_value = None
        
        # First, try to get "GSA BIM Area" from "GSA Space Areas" property set
        if "GSA Space Areas" in psets and "GSA BIM Area" in psets["GSA Space Areas"]:
            area_value = psets["GSA Space Areas"]["GSA BIM Area"]
        # If not found, try to get "Area" from "PSet_Revit_Dimensions" property set
        elif "PSet_Revit_Dimensions" in psets and "Area" in psets["PSet_Revit_Dimensions"]:
            area_value = psets["PSet_Revit_Dimensions"]["Area"]
        
        # Add the area to the total if found
        if area_value is not None:
            total_area += float(area_value)
    
    return total_area