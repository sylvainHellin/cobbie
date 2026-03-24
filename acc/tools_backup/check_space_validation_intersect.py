import ifcopenshell
import ifcopenshell.geom
from typing import List
import multiprocessing


def check_space_validation_intersect(path_ifc_model: str) -> List[str]:
    """
    Check if spaces intersect with building components (walls, slabs, columns, roofs, curtain walls).
    
    This rule checks that space geometry and location are correct. It checks that spaces do not 
    incorrectly intersect with slabs, walls or other components. Components that are fully 
    inside the space are excluded from violations.
    
    Parameters:
        Include: Wall, CurtainWall, Column, Slab, Roof
        Tolerance: 0.03 m
        Check Bottom surface: True
        Check Top surface: False
        Exclude: If component is fully inside the space
    
    Args:
        path_ifc_model: Path to the IFC model file
        
    Returns:
        List of IFC GUIDs of spaces that violate the rule (intersect with components)
        
    Example:
        >>> guids = check_space_validation_intersect("/path/to/model.ifc")
        >>> print(f"Found {len(guids)} violating spaces")
    """
    model = ifcopenshell.open(path_ifc_model)
    
    # Get spaces and relevant components
    spaces = list(model.by_type('IfcSpace'))
    
    component_types = ['IfcWall', 'IfcCurtainWall', 'IfcColumn', 'IfcSlab', 'IfcRoof']
    components = []
    for ifc_class in component_types:
        components.extend(model.by_type(ifc_class))
    
    if not spaces or not components:
        return []
    
    # Build geometry tree with spaces and components that have geometry
    settings = ifcopenshell.geom.settings()
    tree = ifcopenshell.geom.tree()
    
    # Use include parameter to process only relevant elements
    relevant_elements = spaces + components
    iterator = ifcopenshell.geom.iterator(
        settings, 
        model, 
        multiprocessing.cpu_count(),
        include=relevant_elements
    )
    
    added_spaces = []
    added_components = []
    
    if iterator.initialize():
        while True:
            shape = iterator.get()
            element = model.by_id(shape.id)
            tree.add_element(shape)
            
            if element.is_a() == 'IfcSpace':
                added_spaces.append(element)
            elif element.is_a() in component_types:
                added_components.append(element)
            
            if not iterator.next():
                break
    
    if not added_spaces or not added_components:
        return []
    
    # Check intersections with tolerance 0.03
    tolerance = 0.03
    violating_space_guids = set()
    
    for space in added_spaces:
        # Find intersecting components for this space
        clashes = tree.clash_intersection_many(
            [space], 
            added_components, 
            tolerance=tolerance, 
            check_all=True
        )
        
        if clashes:
            # Check if any intersecting component is NOT fully inside the space
            violation_found = False
            for clash in clashes:
                comp = clash.b  # The component
                
                # Check if component is fully inside space using tree.select
                # Elements completely_within the space would be in select(..., completely_within=True)
                try:
                    components_in_space = tree.select(space, completely_within=True)
                    is_fully_inside = comp in components_in_space
                except (AttributeError, RuntimeError):
                    # If select fails, assume not fully inside (conservative)
                    is_fully_inside = False
                
                # If component is NOT fully inside, this is a violation
                if not is_fully_inside:
                    violation_found = True
                    break
            
            if violation_found:
                violating_space_guids.add(space.GlobalId)
    
    return sorted(list(violating_space_guids))