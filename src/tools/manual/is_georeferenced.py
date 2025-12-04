# python packages
import sys
import os
sys.path.insert(0, os.path.dirname(os.getcwd()))

# state management
from state import get_model_path

# ifcopenshell
import ifcopenshell
import ifcopenshell.util.element

def is_georeferenced(model: str = None) -> bool:
    """Check if an IFC model has georeferencing information.
    
    Args:
        model (str, optional): The type of model to analyze - e.g. 'arc' for architectural 
            or 'mep' for MEP model. If None, uses the model from the current state.
            
    Returns:
        bool: True if the model has georeferencing information, False otherwise
    """
    ifc_model = ifcopenshell.open(get_model_path(model=model))
    
    try:
        # Try to get map conversion parameters
        map_conversion = None
        projected_crs = None
        
        # For IFC4+ files
        if hasattr(ifc_model, "schema") and "IFC4" in ifc_model.schema:
            # Look for IfcMapConversion
            map_conversions = ifc_model.by_type("IfcMapConversion")
            if map_conversions:
                map_conversion = map_conversions[0]
            
            # Look for IfcProjectedCRS 
            projected_crss = ifc_model.by_type("IfcProjectedCRS")
            if projected_crss:
                projected_crs = projected_crss[0]
                
        # For IFC2X3 files, check for the ePSet_MapConversion property set on the project
        else:
            project = ifc_model.by_type("IfcProject")[0]
            psets = ifcopenshell.util.element.get_psets(project)
            if "ePSet_MapConversion" in psets:
                map_conversion = psets["ePSet_MapConversion"]
        
        # If we found either map conversion or projected CRS data, the model is georeferenced
        is_georeferenced = bool(map_conversion or projected_crs)
        
        if is_georeferenced:
            print("Model is georeferenced")
            if map_conversion:
                print("Map conversion parameters found")
            if projected_crs:
                print(f"Projected CRS found: {projected_crs.Name if projected_crs else ''}")
        
        return is_georeferenced

    except Exception as e:
        print(f"Error checking georeferencing: {e}")
        return False

if __name__ == "__main__":
    # Test the function with both architectural and MEP models
    print("\nTesting architectural model:")
    print(is_georeferenced(model="arc"))
    
    print("\nTesting MEP model:")
    print(is_georeferenced(model="mep")) 