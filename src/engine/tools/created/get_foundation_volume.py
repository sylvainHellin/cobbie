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


def get_foundation_volume(path_ifc_model: str) -> float:
    """
    Calculate the total volume of main foundation elements in an IFC model.
    
    This function identifies and calculates volume only for main structural foundation elements,
    specifically excluding equipment footings and other non-structural footings.
    
    Main foundation elements considered:
    - IfcFooting elements with PredefinedType = 'STRIP_FOOTING' (wall foundations)
    - IfcSlab elements with PredefinedType = 'BASESLAB' (base slabs)
    
    Assumptions:
    - STRIP_FOOTING elements represent main wall foundations
    - BASESLAB elements represent main foundation slabs
    - Other footing types (NOTDEFINED, etc.) are considered equipment/column footings and excluded
    
    Args:
        path_ifc_model (str): Path to the IFC model file
        
    Returns:
        float: Total volume of main foundation elements in cubic meters (m³)
    """
    # Open the IFC model
    model = ifcopenshell.open(path_ifc_model)
    
    # Initialize total volume
    total_volume = 0.0
    
    # Get all strip footing elements (main wall foundations)
    strip_footings = []
    all_footings = model.by_type("IfcFooting")
    for footing in all_footings:
        if getattr(footing, 'PredefinedType', None) == 'STRIP_FOOTING':
            strip_footings.append(footing)
    
    # Get all base slab elements (main foundation slabs)
    base_slabs = []
    all_slabs = model.by_type("IfcSlab")
    for slab in all_slabs:
        if getattr(slab, 'PredefinedType', None) == 'BASESLAB':
            base_slabs.append(slab)
    
    # Calculate volume for each main foundation element
    foundation_elements = strip_footings + base_slabs
    
    for element in foundation_elements:
        try:
            # Calculate volume using IfcOpenShell's shape utilities
            volume = ifcopenshell.util.shape.get_volume(element)
            if volume is not None and volume > 0:
                total_volume += volume
        except Exception:
            # Skip elements where volume calculation fails
            continue
    
    return total_volume