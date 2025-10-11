import ifcopenshell
import ifcopenshell.util.element
from typing import Dict, List, Optional, Union


def calculate_gross_floor_area(ifc_model_path: str) -> float:
    """
    Calculate the total gross floor area from an IFC model by summing up all space areas.
    
    This function handles different property set naming conventions for area values:
    - Prioritizes "GSA BIM Area" from "GSA Space Areas" property set
    - Falls back to "Area" from "PSet_Revit_Dimensions" property set
    - Additional fallbacks for standard IFC and other BIM software exports
    
    Args:
        ifc_model_path (str): Path to the IFC model file
        
    Returns:
        float: Total gross floor area in square units
        
    Note:
        This function assumes the IFC model contains IfcSpace entities with area properties
        in either "GSA Space Areas" or "PSet_Revit_Dimensions" property sets.
        
        If these specific property sets are not available, the function will fall back
        to standard IFC property sets like "BaseQuantities" with "GrossFloorArea" property,
        which is commonly found in IFC models exported from various BIM authoring software
        including ArchiCAD, Vectorworks, and other IFC-compliant applications.
        
        The function prioritizes gross floor area measurements over net floor area
        to ensure accurate total building area calculations.
    """
    # Load the IFC model
    ifc_model = ifcopenshell.open(ifc_model_path)
    
    # Get all IfcSpace entities
    spaces = ifc_model.by_type("IfcSpace")
    
    total_area = 0.0
    spaces_processed = 0
    spaces_without_area = 0
    
    # Define property search priority based on requirements, with additional fallbacks
    # Each tuple contains (property_set_name, property_name)
    area_property_priorities = [
        ("GSA Space Areas", "GSA BIM Area"),           # Primary requirement: GSA standard
        ("PSet_Revit_Dimensions", "Area"),            # Secondary requirement: Revit export
        ("BaseQuantities", "GrossFloorArea"),         # Standard IFC fallback
        ("Pset_SpaceCommon", "Area"),                 # Common space properties fallback
        ("BaseQuantities", "NetFloorArea"),           # Last resort: net area
    ]
    
    # Process each space
    for space in spaces:
        # Get all property sets for this space
        psets = ifcopenshell.util.element.get_psets(space)
        
        area_value = None
        source_info = None
        
        # Try to find area using priority order
        for pset_name, prop_name in area_property_priorities:
            if pset_name in psets and prop_name in psets[pset_name]:
                area_value = psets[pset_name][prop_name]
                source_info = f"{pset_name}.{prop_name}"
                break
        
        # If still not found, search for any "Area" property in any property set
        if area_value is None:
            for pset_name, properties in psets.items():
                if "Area" in properties:
                    area_value = properties["Area"]
                    source_info = f"{pset_name}.Area"
                    break
        
        # Add the area to the total if found
        if area_value is not None:
            try:
                area_float = float(area_value)
                if area_float > 0:  # Only add positive areas
                    total_area += area_float
                    spaces_processed += 1
                else:
                    spaces_without_area += 1
            except (ValueError, TypeError):
                spaces_without_area += 1
        else:
            spaces_without_area += 1
    
    # Optional: Log processing statistics
    if spaces_without_area > 0:
        print(f"Warning: {spaces_without_area} out of {len(spaces)} spaces had no valid area information")
    
    return total_area