import ifcopenshell
import ifcopenshell.util.element
from typing import List, Set, Dict, Optional


def check_504_2_stair_slab_connection(path_ifc_model: str) -> List[str]:
    """
    Rule: 504.2 504_2_stair_slab_connection
    504.2 Treads and Risers
    All stairs shall be connected to slabs.

    Parameters: Stair Classification: Stair*

    Question: What stairs in the current IFC model are not properly connected to slabs?

    This function identifies stairs that are not properly connected to floor slabs by:
    1. Finding all IfcStair elements
    2. Identifying floor slabs (excluding landing slabs that are part of stair assemblies)
    3. Checking if each stair shares a building storey with at least one floor slab
    4. A stair is considered a violation if no floor slab exists in the same storey

    Args:
        path_ifc_model: Path to the IFC model file.

    Returns:
        List of IFC GUIDs of all stair elements that violate this rule
        (stairs not connected to any floor slab in the same building storey).

    Example:
        >>> violations = check_504_2_stair_slab_connection("/path/to/model.ifc")
        >>> print(violations)
        ['3NhaIUfh12PAdrGa$S3z3M', '0mxk1RW8H5mvX1dNnpRqBK']
    """
    model = ifcopenshell.open(path_ifc_model)
    
    # Get all stairs
    stairs = model.by_type('IfcStair')
    if not stairs:
        return []
    
    # Get all slabs
    slabs = model.by_type('IfcSlab')
    
    # Identify landing slabs (slabs that are decomposed from stairs)
    # These are part of the stair assembly, not actual floor slabs
    landing_slab_guids: Set[str] = set()
    for slab in slabs:
        try:
            for rel in slab.Decomposes:
                if hasattr(rel, 'RelatingObject'):
                    relating = rel.RelatingObject
                    if relating and relating.is_a('IfcStair'):
                        landing_slab_guids.add(slab.GlobalId)
        except AttributeError:
            continue
    
    # Get only floor slabs (not landing slabs)
    floor_slabs = [s for s in slabs if s.GlobalId not in landing_slab_guids]
    
    # Map floor slabs to their storeys
    floor_slabs_by_storey: Dict[int, List] = {}
    for slab in floor_slabs:
        try:
            storey = ifcopenshell.util.element.get_container(slab)
            if storey:
                storey_id = storey.id()
                if storey_id not in floor_slabs_by_storey:
                    floor_slabs_by_storey[storey_id] = []
                floor_slabs_by_storey[storey_id].append(slab)
        except (AttributeError, RuntimeError):
            continue
    
    # Check each stair for connection to floor slabs in the same storey
    violations: List[str] = []
    for stair in stairs:
        try:
            storey = ifcopenshell.util.element.get_container(stair)
            if not storey:
                # Stair not in a storey - consider it a violation
                violations.append(stair.GlobalId)
                continue
            
            storey_id = storey.id()
            
            # Check if there are floor slabs in the same storey
            slabs_in_storey = floor_slabs_by_storey.get(storey_id, [])
            
            if len(slabs_in_storey) == 0:
                # No floor slab in the same storey - violation
                violations.append(stair.GlobalId)
        except (AttributeError, RuntimeError):
            # If we can't determine the container, skip this stair
            continue
    
    return violations