import ifcopenshell
import ifcopenshell.util.element
from typing import *

def calculate_usable_floor_area(ifc_model_path: str) -> float:
    """
    Calculate the total usable floor area by summing the areas of IfcSlab entities
    with PredefinedType='FLOOR' using data from the PSet_Revit_Dimensions property set.
    
    This function excludes slabs that are likely structural elements (very large or very small)
    to calculate the actual usable floor area.
    
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
        
        This function also applies a size filter to exclude structural slabs that are either
        too large (likely foundation slabs) or too small (non-usable elements).
        
        This function assumes area values in PSet_Revit_Dimensions are already in square meters,
        which is the standard for Revit-exported IFC models.
        
        Size filtering criteria:
        - Minimum usable area: 1.0 sqm (to include small but valid floor areas)
        - Maximum usable area: 10000.0 sqm (to exclude likely foundation slabs)
    """
    # Load the IFC model
    model = ifcopenshell.open(ifc_model_path)
    
    # Find all IfcSlab entities with PredefinedType='FLOOR'
    slabs = [slab for slab in model.by_type("IfcSlab") 
             if hasattr(slab, 'PredefinedType') and slab.PredefinedType == 'FLOOR']
    
    total_area = 0.0
    processed_global_ids = set()  # To ensure we only count each distinct slab once
    
    # For each slab, get the area from property sets
    for slab in slabs:
        # Check for unique GlobalId to avoid counting duplicates
        if slab.GlobalId in processed_global_ids:
            continue
        processed_global_ids.add(slab.GlobalId)
        
        # Get property sets for this slab
        property_sets = ifcopenshell.util.element.get_psets(slab)
        
        # Look for area in PSet_Revit_Dimensions
        if 'PSet_Revit_Dimensions' in property_sets:
            pset_dimensions = property_sets['PSet_Revit_Dimensions']
            if 'Area' in pset_dimensions:
                area_value = pset_dimensions['Area']
                # Apply size filtering to exclude structural slabs that are either
                # too large (likely foundation slabs) or too small (non-usable elements)
                if 1.0 <= area_value <= 10000.0:
                    total_area += area_value
    
    return float(total_area)