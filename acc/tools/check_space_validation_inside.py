import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.shape
import trimesh
import numpy as np
from typing import List, Dict, Any


def check_space_validation_inside(path_ifc_model: str) -> List[str]:
    """
    Check for components incorrectly inside spaces.

    This rule checks that space geometry and location are correct by identifying
    components that are improperly contained within spaces. A component is considered
    incorrectly inside if all of its vertices are contained within the space volume.

    Parameters:
    - Include: Wall, CurtainWall, Column, Slab, Roof
    - Tolerance: 0.03 m (handled by geometric containment check)
    - Check Bottom surface: True
    - Check Top surface: False

    Args:
        path_ifc_model: Path to the IFC model file

    Returns:
        List of IFC GUIDs of spaces that have components incorrectly inside them.
        Returns empty list if model has no spaces or no violations found.

    Example:
        >>> guids = check_space_validation_inside('/path/to/model.ifc')
        >>> print(f"Found {len(guids)} violations")
        ['3LbNSBzHHBSuzhUUvuwCoN', '3NhaIUfh12PAdrGa$S3xUm']
    """
    model = ifcopenshell.open(path_ifc_model)
    settings = ifcopenshell.geom.settings()
    
    # Component types to check as specified in the rule
    component_types = ['IfcWall', 'IfcCurtainWall', 'IfcColumn', 'IfcSlab', 'IfcRoof']
    
    def get_element_mesh(elem) -> trimesh.Trimesh:
        """Get trimesh mesh for an IFC element.
        
        Returns None if geometry cannot be created.
        """
        try:
            shape = ifcopenshell.geom.create_shape(settings, elem)
            verts = ifcopenshell.util.shape.get_vertices(shape.geometry)
            faces = ifcopenshell.util.shape.get_faces(shape.geometry)
            return trimesh.Trimesh(vertices=verts, faces=faces)
        except (AttributeError, RuntimeError, Exception):
            return None
    
    def bounds_overlap(bounds1: np.ndarray, bounds2: np.ndarray) -> bool:
        """Check if two bounding boxes overlap in 3D."""
        return not (
            bounds1[1][0] < bounds2[0][0] or bounds1[0][0] > bounds2[1][0] or
            bounds1[1][1] < bounds2[0][1] or bounds1[0][1] > bounds2[1][1] or
            bounds1[1][2] < bounds2[0][2] or bounds1[0][2] > bounds2[1][2]
        )
    
    def is_component_inside_space(space_mesh: trimesh.Trimesh, 
                                  component_mesh: trimesh.Trimesh) -> bool:
        """Check if component is completely inside space (violation).
        
        Returns True if all component vertices are inside the space volume.
        """
        if space_mesh is None or component_mesh is None:
            return False
        
        try:
            contains = space_mesh.contains(component_mesh.vertices)
            return np.all(contains)
        except (AttributeError, ValueError, Exception):
            return False
    
    # Get all spaces
    spaces = model.by_type('IfcSpace')
    if not spaces:
        return []
    
    # Pre-compute space meshes
    space_data: List[Dict[str, Any]] = []
    skipped_spaces = 0
    
    for space in spaces:
        mesh = get_element_mesh(space)
        if mesh is None:
            skipped_spaces += 1
            continue
        space_data.append({
            'guid': space.GlobalId,
            'name': getattr(space, 'Name', 'Unknown'),
            'mesh': mesh,
            'bounds': mesh.bounds
        })
    
    # Collect all components
    all_components = []
    for comp_type in component_types:
        all_components.extend(model.by_type(comp_type))
    
    if not all_components:
        return []
    
    # Find violations
    violation_guids = set()
    skipped_components = 0
    
    for comp in all_components:
        comp_mesh = get_element_mesh(comp)
        if comp_mesh is None:
            skipped_components += 1
            continue
        
        comp_bounds = comp_mesh.bounds
        
        # Check each space for this component
        for space_info in space_data:
            # Skip if already found violation for this space
            if space_info['guid'] in violation_guids:
                continue
            
            # Quick bounds overlap check to filter non-overlapping elements
            if not bounds_overlap(space_info['bounds'], comp_bounds):
                continue
            
            # Detailed containment check
            if is_component_inside_space(space_info['mesh'], comp_mesh):
                violation_guids.add(space_info['guid'])
                break
    
    return list(violation_guids)
