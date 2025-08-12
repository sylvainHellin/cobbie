import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.shape

def calculate_usable_floor_area(ifc_model_path: str) -> float:
    """
    Calculate the total usable floor area from an IFC model.
    
    This function identifies all IfcSlab entities with PredefinedType='FLOOR',
    calculates their geometric footprint areas (projected on the XY plane), 
    and returns the sum as the total usable floor area.
    
    Args:
        ifc_model_path (str): Path to the IFC model file.
        
    Returns:
        float: Total usable floor area in square units.
        
    Raises:
        FileNotFoundError: If the IFC model file cannot be found.
        Exception: If there are issues processing the IFC model or calculating areas.
        
    Note:
        This function assumes that usable floor area corresponds to IfcSlab entities
        with PredefinedType='FLOOR' in the IFC model. The area calculation is based
        on the footprint area (XY plane projection) of these slabs, which represents 
        the usable floor area.
        
        This function uses IfcOpenShell's get_footprint_area utility with Z-axis 
        projection to calculate the top-down projected area of floor slabs.
    """
    # Load the IFC model
    try:
        model = ifcopenshell.open(ifc_model_path)
    except FileNotFoundError:
        raise FileNotFoundError(f"IFC model file not found: {ifc_model_path}")
    except Exception as e:
        raise Exception(f"Error loading IFC model: {e}")
    
    # Find all IfcSlab entities with PredefinedType='FLOOR'
    slabs = model.by_type("IfcSlab")
    floor_slabs = [slab for slab in slabs if getattr(slab, 'PredefinedType', None) == 'FLOOR']
    
    if not floor_slabs:
        return 0.0
    
    # Configure geometry settings
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    
    total_area = 0.0
    
    # Calculate footprint area for each floor slab
    for slab in floor_slabs:
        try:
            shape = ifcopenshell.geom.create_shape(settings, slab)
            geometry = shape.geometry
            
            # Calculate footprint area using IfcOpenShell utility
            # This calculates the area projected on the XY plane (Z-axis projection)
            area = ifcopenshell.util.shape.get_footprint_area(geometry)
            total_area += area
            
        except Exception as e:
            # Skip slabs that cannot be processed
            continue
    
    return total_area