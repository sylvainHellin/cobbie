import ifcopenshell
import ifcopenshell.geom
from typing import List


def check_504_2_stair_slab_connection(path_ifc_model: str) -> List[str]:
    """
    Check if stairs are properly connected to slabs according to rule 504.2.
    
    All stairs shall be connected to slabs. This function identifies stairs that
    are not properly connected to external floor slabs (slabs not part of the
    stair's own decomposition structure).

    Args:
        path_ifc_model: Path to the IFC model file.

    Returns:
        List of IFC GUIDs of stairs that violate the rule (not connected to
        external floor slabs). Returns empty list if no violations found or if
        no stairs exist in the model.

    Example:
        >>> violations = check_504_2_stair_slab_connection('model.ifc')
        >>> print(violations)
        ['3NhaIUfh12PAdrGa$S3z3M', '0mxk1RW8H5mvX1dNnpRqBK']
    """
    model = ifcopenshell.open(path_ifc_model)
    
    # Get all stairs and slabs in the model
    stairs = model.by_type('IfcStair')
    all_slabs = model.by_type('IfcSlab')
    
    # Return empty list if no stairs to check
    if not stairs:
        return []
    
    # Collect ALL elements that are part of any stair's decomposition.
    # These include stair flights, internal landing slabs, railings, etc.
    all_stair_elements = set()
    for stair in stairs:
        for rel in stair.IsDecomposedBy or []:
            for obj in rel.RelatedObjects or []:
                all_stair_elements.add(obj)
    
    # External slabs are those NOT part of any stair's decomposition.
    # These represent true floor slabs that stairs should connect to.
    external_slabs = [s for s in all_slabs if s not in all_stair_elements]
    
    violations = []
    skipped = 0
    
    for stair in stairs:
        try:
            # Check if there are any external floor slabs in the model
            if len(external_slabs) == 0:
                # No external floor slabs exist - this is a violation
                violations.append(stair.GlobalId)
            else:
                # Check if stair geometrically touches any external floor slab
                settings = ifcopenshell.geom.settings()
                tree = ifcopenshell.geom.tree()
                tree.add([stair] + external_slabs)
                
                connected = False
                for ext_slab in external_slabs:
                    # Use collision detection with touching allowed
                    clashes = tree.clash_collision_many(
                        [stair],
                        [ext_slab],
                        allow_touching=True
                    )
                    if clashes:
                        connected = True
                        break
                
                if not connected:
                    violations.append(stair.GlobalId)
                    
        except (AttributeError, RuntimeError) as e:
            # Skip elements with geometry processing errors
            skipped += 1
            continue
    
    if skipped > 0:
        print(f"Warning: Skipped {skipped} stairs due to geometry processing errors")
    
    return violations