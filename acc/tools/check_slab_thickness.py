import ifcopenshell
import ifcopenshell.util.element
from typing import List


def check_slab_thickness(path_ifc_model: str) -> List[str]:
    """
    Rule: BIM Validation - Slab Thickness
    
    Checks that slab thickness is not too small or too large.
    Minimum thickness 0.03 m, maximum 1.0 m.
    
    Excludes slab elements with predefined types: Fixed Furnishings, Suspended Ceilings.
    
    Args:
        path_ifc_model: Path to the IFC model file
        
    Returns:
        List of IFC GUIDs of all slab elements that violate the thickness rule.
        Returns empty list if model is empty or no violations found.
        
    Example:
        >>> guids = check_slab_thickness('/path/to/model.ifc')
        >>> print(f'Found {len(guids)} violations')
    """
    model = ifcopenshell.open(path_ifc_model)
    
    # Get all slabs
    slabs = model.by_type('IfcSlab')
    if not slabs:
        return []
    
    min_thickness = 0.03
    max_thickness = 1.0
    exclude_types = {'FIXEDFURNISHINGS', 'SUSPENDEDCEILING'}
    
    violating_guids = []
    skipped = 0
    
    for slab in slabs:
        try:
            # Skip excluded predefined types
            predefined_type = getattr(slab, 'PredefinedType', None)
            if predefined_type and predefined_type.upper() in exclude_types:
                continue
            
            # Get thickness from property sets (check element first, then type)
            psets = ifcopenshell.util.element.get_psets(slab)
            thickness = None
            
            # Common pset names that may contain thickness
            pset_names_to_check = [
                'PSet_Revit_Dimensions',
                'Pset_SlabCommon', 
                'Qto_SlabBaseQuantities',
                'Pset_Revit_Type_Construction'
            ]
            
            for pset_name in pset_names_to_check:
                if pset_name in psets:
                    pset_data = psets[pset_name]
                    # Try case-insensitive key search for Thickness
                    for key in pset_data:
                        if key.upper() == 'THICKNESS':
                            thickness = pset_data[key]
                            break
                if thickness is not None:
                    break
            
            # If not found in element psets, check type psets
            if thickness is None:
                slab_type = ifcopenshell.util.element.get_type(slab)
                if slab_type:
                    type_psets = ifcopenshell.util.element.get_psets(slab_type)
                    for pset_name in pset_names_to_check:
                        if pset_name in type_psets:
                            pset_data = type_psets[pset_name]
                            for key in pset_data:
                                if key.upper() == 'THICKNESS':
                                    thickness = pset_data[key]
                                    break
                        if thickness is not None:
                            break
            
            if thickness is not None:
                try:
                    thickness_val = float(thickness)
                    if thickness_val < min_thickness or thickness_val > max_thickness:
                        violating_guids.append(slab.GlobalId)
                except (TypeError, ValueError):
                    skipped += 1
                    continue
            else:
                skipped += 1
                continue
                
        except (AttributeError, KeyError, RuntimeError):
            skipped += 1
            continue
    
    if skipped > 0:
        print(f'Warning: Skipped {skipped} elements due to missing or invalid thickness data')
    
    return violating_guids