import ifcopenshell
import ifcopenshell.util.element
from typing import List

def check_504_2_stair_slab_connection(path_ifc_model: str) -> List[str]:
    """
    Check if all stairs are properly connected to slabs in the IFC model.
    
    A stair is considered connected to slabs if it resides in the same building storey
    as at least one external floor slab. External slabs are those that are NOT part
    of a stair assembly (i.e., not decomposed by an IfcRelAggregates relationship
    where the relating object is an IfcStair).

    Args:
        path_ifc_model: Path to the IFC model file

    Returns:
        List of IFC GUIDs of stair elements that are not properly connected to slabs.
        Returns an empty list if the model contains no stairs or if all stairs are
        properly connected.

    Raises:
        RuntimeError: If the IFC file cannot be opened.

    Example:
        >>> guids = check_504_2_stair_slab_connection('/path/to/model.ifc')
        >>> print(f'Violations: {len(guids)}')
        >>> for guid in guids:
        ...     print(f'  {guid}')
    """
    # Open the model
    model = ifcopenshell.open(path_ifc_model)
    
    violations: List[str] = []
    skipped: int = 0
    
    # Get all stairs and slabs
    stairs = model.by_type('IfcStair')
    slabs = model.by_type('IfcSlab')
    
    # Early return if no stairs in the model
    if not stairs:
        return []
    
    # Function to check if a slab is internal to a stair assembly
    def is_internal_to_stair(slab) -> bool:
        """Check if a slab is part of a stair assembly (decomposed by IfcStair)."""
        try:
            inverses = model.get_inverse(slab)
            for rel in inverses:
                if rel.is_a() == 'IfcRelAggregates':
                    relating_obj = rel.RelatingObject
                    if relating_obj and relating_obj.is_a() == 'IfcStair':
                        return True
        except (AttributeError, RuntimeError):
            pass
        return False
    
    # Filter slabs to identify external (building floor) slabs
    external_slabs = []
    for slab in slabs:
        try:
            if not is_internal_to_stair(slab):
                external_slabs.append(slab)
        except (AttributeError, RuntimeError):
            skipped += 1
            continue
    
    # Build a set of storey GUIDs that contain external slabs
    external_slab_storeys = set()
    for slab in external_slabs:
        try:
            container = ifcopenshell.util.element.get_container(slab)
            if container is not None:
                external_slab_storeys.add(container.GlobalId)
        except (AttributeError, RuntimeError):
            skipped += 1
            continue
    
    # Check each stair for connection to external slabs
    for stair in stairs:
        try:
            container = ifcopenshell.util.element.get_container(stair)
            
            if container is None:
                # Stair not in any storey - violation
                violations.append(stair.GlobalId)
            elif container.GlobalId not in external_slab_storeys:
                # Stair in a storey without any external slabs - violation
                violations.append(stair.GlobalId)
            
        except (AttributeError, RuntimeError):
            skipped += 1
            continue
    
    if skipped > 0:
        print(f"Warning: Skipped {skipped} elements due to errors")
    
    return violations