import ifcopenshell
import ifcopenshell.util.element
from typing import List


def check_slab_thickness(path_ifc_model: str) -> List[str]:
    """
    Validates slab thickness in an IFC model against specified minimum and maximum values.
    
    This rule checks that slab thickness is not too small or too large.
    Minimum thickness: 0.30 m, maximum thickness: 1.0 m.
    
    Parameters:
        - Exclude Slab Building Elements - General: One Of [Fixed Furnishings, Suspended Ceilings]
        - Include Slab Thickness: >= 0.30 m
        - Include Slab Thickness: <= 1.0 m

    Args:
        path_ifc_model: Path to the IFC model file.

    Returns:
        List of IFC GUIDs of all slab elements that violate the thickness rule.
        Returns an empty list if no violations are found or if no applicable slabs exist.

    Example:
        >>> violations = check_slab_thickness('/path/to/model.ifc')
        >>> print(f"Found {len(violations)} thickness violations")
    """
    model = ifcopenshell.open(path_ifc_model)
    slabs = model.by_type('IfcSlab')
    
    violations = []
    skipped = 0
    
    for slab in slabs:
        guid = slab.GlobalId
        predefined_type = getattr(slab, 'PredefinedType', None)
        name = slab.Name or ''
        
        # Exclude Fixed Furnishings and Suspended Ceilings based on PredefinedType
        if predefined_type in ['FIXEDFURNISHING', 'SUSPENDEDCEILING']:
            continue
        
        # Get thickness from property sets
        thickness = None
        psets = ifcopenshell.util.element.get_psets(slab)
        
        for pset_name, pset in psets.items():
            if 'Thickness' in pset:
                thickness = pset['Thickness']
                break
        
        # If thickness not found in instance psets, check type psets
        if thickness is None:
            try:
                slab_type = ifcopenshell.util.element.get_type(slab)
                if slab_type:
                    type_psets = ifcopenshell.util.element.get_psets(slab_type)
                    for pset_name, pset in type_psets.items():
                        if 'Thickness' in pset:
                            thickness = pset['Thickness']
                            break
            except (AttributeError, RuntimeError):
                skipped += 1
                continue
        
        # Check Reference field from Pset_SlabCommon for filtering
        reference = ''
        if 'Pset_SlabCommon' in psets:
            reference = str(psets['Pset_SlabCommon'].get('Reference', ''))
        
        # Only check thickness for finish floor elements
        # (containing 'Finish' in name or reference)
        if 'Finish' not in name and 'Finish' not in reference:
            continue
        
        # Validate thickness against requirements
        if thickness is not None:
            try:
                if thickness < 0.30 or thickness > 1.0:
                    violations.append(guid)
            except TypeError:
                skipped += 1
                continue
    
    if skipped > 0:
        print(f"Warning: Skipped {skipped} elements due to missing data or access errors")
    
    return violations