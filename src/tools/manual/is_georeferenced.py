# ifcopenshell
import ifcopenshell
import ifcopenshell.util.element

def is_georeferenced(model_path: str) -> bool:
    """Check if an IFC model has georeferencing information.

    Args:
        model_path (str): Absolute path to the IFC model file to analyze.
            
    Returns:
        bool: True if the model has georeferencing information, False otherwise
    """
    ifc_model = ifcopenshell.open(model_path)
    
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