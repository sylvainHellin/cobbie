import ifcopenshell
import ifcopenshell.util.element
from typing import *

def calculate_usable_floor_area(ifc_model_path: str) -> float:
    """
    Calculate the total usable floor area by summing the areas of IfcSlab entities 
    with PredefinedType='FLOOR' using data from the PSet_Revit_Dimensions property set.
    
    Args:
        ifc_model_path (str): Path to the IFC model file
        
    Returns:
        float: Total usable floor area in square meters
        
    Note:
        This function assumes the IFC model contains IfcSlab entities with 
        PredefinedType='FLOOR' and PSet_Revit_Dimensions property sets with 'Area' property.
        It's specifically designed for IFC models exported from Revit.
        
        The function filters out slabs that might be duplicated or represent non-usable areas
        by checking for unique GlobalId values and ensuring we only count each distinct slab once.
    """
    # Load the IFC model
    model = ifcopenshell.open(ifc_model_path)
    
    # Find all IfcSlab entities with PredefinedType='FLOOR'
    floor_slabs = [slab for slab in model.by_type("IfcSlab") if getattr(slab, 'PredefinedType', None) == "FLOOR"]
    
    total_area = 0.0
    processed_slabs = set()  # To avoid double counting
    
    # For each floor slab, get the area from PSet_Revit_Dimensions
    for slab in floor_slabs:
        # Skip if we've already processed this slab (avoid double counting)
        if slab.GlobalId in processed_slabs:
            continue
            
        # Get property sets for this slab
        property_sets = ifcopenshell.util.element.get_psets(slab)
        
        # Check if PSet_Revit_Dimensions exists and has an 'Area' property
        if "PSet_Revit_Dimensions" in property_sets:
            pset_dimensions = property_sets["PSet_Revit_Dimensions"]
            if "Area" in pset_dimensions:
                # Add the area to our total
                total_area += pset_dimensions["Area"]
                # Mark this slab as processed
                processed_slabs.add(slab.GlobalId)
    
    return float(total_area)