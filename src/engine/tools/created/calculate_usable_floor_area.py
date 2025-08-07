
import ifcopenshell
import ifcopenshell.util.element
from typing import Union

def calculate_usable_floor_area(model: Union[str, ifcopenshell.file]) -> float:
    """
    Calculate the Usable Floor Area (UFA) by aggregating space areas from an IFC model.
    
    This function extracts area properties from IfcSpace elements, typically found in 
    property sets like 'PSet_Revit_Dimensions.Area' or 'GSA Space Areas.GSA BIM Area'.
    It is primarily designed for IFC models exported from Revit software.
    
    Args:
        model: Path to an IFC file or an already loaded ifcopenshell.file object
        
    Returns:
        float: Total usable floor area in square meters (or the model's units)
        
    Raises:
        ValueError: If the model is invalid or no spaces are found
        FileNotFoundError: If a file path is provided but the file doesn't exist
    """
    # Load the model if a path is provided
    if isinstance(model, str):
        try:
            model = ifcopenshell.open(model)
        except Exception as e:
            raise FileNotFoundError(f"Could not open IFC file at {model}: {str(e)}")
    
    # Get all IfcSpace elements
    spaces = model.by_type("IfcSpace")
    
    if not spaces:
        raise ValueError("No IfcSpace elements found in the model")
    
    total_area = 0.0
    
    # Iterate through all spaces and extract area properties
    for space in spaces:
        # Get property sets for this space
        property_sets = ifcopenshell.util.element.get_psets(space)
        
        # Try to get area from PSet_Revit_Dimensions first (primary source)
        area = None
        if "PSet_Revit_Dimensions" in property_sets:
            dimensions_pset = property_sets["PSet_Revit_Dimensions"]
            if "Area" in dimensions_pset:
                area = dimensions_pset["Area"]
        
        # Fallback to GSA Space Areas if Revit dimensions not available
        if area is None and "GSA Space Areas" in property_sets:
            gsa_pset = property_sets["GSA Space Areas"]
            if "GSA BIM Area" in gsa_pset:
                area = gsa_pset["GSA BIM Area"]
        
        # Add to total if area was found
        if area is not None:
            total_area += float(area)
        else:
            print(f"Warning: No area property found for space {space.GlobalId} ({space.Name})")
    
    return total_area
