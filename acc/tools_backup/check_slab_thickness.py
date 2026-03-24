import ifcopenshell
import ifcopenshell.util.element
from typing import List

def check_slab_thickness(path_ifc_model: str) -> List[str]:
    """
    Rule: BIM Validation: Slab Thickness slab_thickness
    
    Checks that slab thickness is not too small or too large.
    Minimum thickness: 0.30 m, Maximum thickness: 1.0 m.
    
    Excludes slabs with PredefinedType 'FIXED_FURNISHING' or 'SUSPENDED_CEILING'.
    
    Args:
        path_ifc_model: Path to the IFC model file.
        
    Returns:
        List of IFC GUIDs of all slab elements that violate the thickness rule.
        Returns empty list if no violations found or no valid slabs to check.
        
    Example:
        >>> violating_guids = check_slab_thickness('model.ifc')
        >>> print(f'Found {len(violating_guids)} violations')
    """
    # Define parameters
    MIN_THICKNESS = 0.30  # meters
    MAX_THICKNESS = 1.0   # meters
    EXCLUDED_TYPES = {'FIXED_FURNISHING', 'SUSPENDED_CEILING'}
    
    # Open the IFC model
    model = ifcopenshell.open(path_ifc_model)
    
    violating_guids = []
    skipped_count = 0
    
    # Get all IfcSlab elements
    slabs = model.by_type('IfcSlab')
    
    if not slabs:
        return []
    
    for slab in slabs:
        try:
            # Check if slab should be excluded based on PredefinedType
            predefined_type = getattr(slab, 'PredefinedType', None)
            if predefined_type in EXCLUDED_TYPES:
                continue
            
            # Exclude slabs on grade - these are structural foundation slabs
            slab_name = getattr(slab, 'Name', '')
            if 'Slab on Grade' in slab_name:
                continue
            
            # Get all psets (both properties and quantities)
            # Thickness can be in properties like PSet_Revit_Dimensions
            all_psets = ifcopenshell.util.element.get_psets(slab)
            
            # Look for thickness in any pset (properties or quantities)
            thickness = None
            for pset_name, pset in all_psets.items():
                if 'Thickness' in pset:
                    thickness = pset['Thickness']
                    break
            
            if thickness is None:
                skipped_count += 1
                continue
            
            # Check if thickness violates rules
            if thickness < MIN_THICKNESS or thickness > MAX_THICKNESS:
                violating_guids.append(slab.GlobalId)
                
        except (AttributeError, KeyError, TypeError):
            skipped_count += 1
            continue
    
    if skipped_count > 0:
        print(f"Warning: Skipped {skipped_count} elements due to missing data or errors")
    
    return violating_guids