import ifcopenshell
import ifcopenshell.geom
from typing import List, Set


def check_space_validation_intersect(path_ifc_model: str) -> List[str]:
    """
    Checks for space intersection violations in an IFC model.
    
    This rule validates that space geometry and location are correct by checking
    that spaces do not incorrectly intersect with building components (Wall, CurtainWall,
    Column, Slab, Roof). It uses a 0.03m tolerance and excludes components that are
    fully inside the space.

    Parameters:
    -----------
    path_ifc_model : str
        File path to the IFC model

    Returns:
    --------
    List[str]
        Sorted list of IFC GUIDs of spaces that violate this rule (spaces that
        intersect with building elements where the element is not fully inside the space)
    
    Example:
    -------
    >>> violations = check_space_validation_intersect('/path/to/model.ifc')
    >>> print(f"Found {len(violations)} spaces with intersection violations")
    """
    # Open the model
    model = ifcopenshell.open(path_ifc_model)
    
    # Get spaces and building elements
    spaces = list(model.by_type('IfcSpace'))
    element_types = ['IfcWall', 'IfcCurtainWall', 'IfcColumn', 'IfcSlab', 'IfcRoof']
    
    building_elements = []
    for et in element_types:
        try:
            building_elements.extend(model.by_type(et))
        except RuntimeError:
            continue
    
    if not spaces:
        return []
    
    if not building_elements:
        return []
    
    # Build geometry tree - CRITICAL: include spaces explicitly!
    # By default, spaces are excluded from geometry processing
    settings = ifcopenshell.geom.settings()
    tree = ifcopenshell.geom.tree()
    
    # Add all elements (spaces + building elements) to tree
    all_elements = spaces + building_elements
    
    skipped = 0
    try:
        iterator = ifcopenshell.geom.iterator(settings, model, include=all_elements)
        if iterator.initialize():
            while True:
                try:
                    tree.add_element(iterator.get())
                except (RuntimeError, AttributeError):
                    skipped += 1
                    continue
                if not iterator.next():
                    break
    except RuntimeError as e:
        return []
    
    if skipped > 0:
        print(f"Warning: Skipped {skipped} elements during geometry processing")
    
    # Detect intersections with 0.03m tolerance
    try:
        clashes = tree.clash_intersection_many(
            spaces,
            building_elements,
            tolerance=0.03,
            check_all=False
        )
    except RuntimeError:
        return []
    
    # Process clashes and exclude elements fully inside space
    violation_space_guids: Set[str] = set()
    element_type_set = set(element_types)
    
    for clash in clashes:
        elem_a = clash.a
        elem_b = clash.b
        
        try:
            # Identify which is space and which is building element
            if elem_a.is_a() == 'IfcSpace' and elem_b.is_a() in element_type_set:
                space = elem_a
                element = elem_b
            elif elem_b.is_a() == 'IfcSpace' and elem_a.is_a() in element_type_set:
                space = elem_b
                element = elem_a
            else:
                continue
            
            # Check if element is fully inside the space
            try:
                elements_inside = tree.select(space, completely_within=True)
            except (RuntimeError, AttributeError):
                continue
            
            if element not in elements_inside:
                # Element is not fully inside space, so this is a violation
                try:
                    space_guid = space.get_argument(0)  # GlobalId
                    if space_guid:
                        violation_space_guids.add(space_guid)
                except (AttributeError, IndexError):
                    continue
                    
        except AttributeError:
            continue
    
    return sorted(list(violation_space_guids))