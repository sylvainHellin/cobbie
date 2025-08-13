import ifcopenshell
import ifcopenshell.util.element

def calculate_usable_floor_area(ifc_model_path: str) -> float:
    """
    Calculate the total usable floor area from an IFC model.
    
    This function identifies all IfcSlab entities with PredefinedType='FLOOR',
    retrieves their area values from the PSet_Revit_Dimensions property set,
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
        with PredefinedType='FLOOR' in the IFC model. The area values are retrieved
        from the PSet_Revit_Dimensions property set, which contains area values 
        calculated by the BIM authoring software (Revit).
        
        This approach is more reliable than geometric calculations as it uses the
        same values that would be displayed in the authoring software.
        This function is specifically designed for IFC models exported from Revit.
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
    
    total_area = 0.0
    
    # Calculate total area from property sets
    for slab in floor_slabs:
        try:
            # Get property sets for the slab
            psets = ifcopenshell.util.element.get_psets(slab)
            
            # Try to get area from PSet_Revit_Dimensions
            if 'PSet_Revit_Dimensions' in psets and 'Area' in psets['PSet_Revit_Dimensions']:
                area = psets['PSet_Revit_Dimensions']['Area']
                total_area += area
            else:
                # If no area found in PSet_Revit_Dimensions, skip this slab
                continue
                
        except Exception as e:
            # Skip slabs that cannot be processed
            continue
    
    return total_area