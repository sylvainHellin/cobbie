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
    """
    # Load the IFC model
    model = ifcopenshell.open(ifc_model_path)
    
    # Find all IfcSlab entities
    slabs = model.by_type("IfcSlab")
    
    total_area = 0.0
    processed_slabs = set()  # To ensure we count each slab only once
    
    # Size thresholds for filtering structural elements
    # Slabs outside these ranges are likely structural elements not part of usable floor area
    MIN_USABLE_AREA = 20.0  # sqm - Increased threshold to exclude small structural elements
    MAX_USABLE_AREA = 2000.0  # sqm - exclude very large foundation slabs
    
    # For each slab, get the area from property sets if it's a FLOOR type
    for slab in slabs:
        # Ensure we process each slab only once
        if slab.GlobalId in processed_slabs:
            continue
        processed_slabs.add(slab.GlobalId)
        
        # Only process slabs with PredefinedType='FLOOR'
        if getattr(slab, 'PredefinedType', None) != 'FLOOR':
            continue
            
        # Get property sets for this slab
        property_sets = ifcopenshell.util.element.get_psets(slab)
        
        # Look for area in PSet_Revit_Dimensions
        if 'PSet_Revit_Dimensions' in property_sets:
            pset_dimensions = property_sets['PSet_Revit_Dimensions']
            if 'Area' in pset_dimensions:
                area_value = pset_dimensions['Area']
                
                # Apply size filters to exclude structural elements
                if MIN_USABLE_AREA <= area_value <= MAX_USABLE_AREA:
                    total_area += area_value
    
    return float(total_area)