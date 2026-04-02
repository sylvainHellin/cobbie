import ifcopenshell
import ifcopenshell.geom
import trimesh
import numpy as np
from typing import List
import logging

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

def check_space_validation_inside(path_ifc_model: str) -> List[str]:
    """
    Rule: General Space Check: Space Validation space_validation_inside
    
    This rule checks that space geometry and location are correct. It also checks
    intersections (inside only) with other components. This template focuses only on
    the 'inside' check: components that are inside the space.
    
    Parameters:
    - Include: Wall, CurtainWall, Column, Slab, Roof
    - Tolerance: 0.03 m
    - Check Bottom surface: True
    - Check Top surface: False
    
    Args:
        path_ifc_model (str): Path to the IFC model file.
    
    Returns:
        List[str]: List of IFC GUIDs of spaces that have components incorrectly
                   inside them (violating the rule).
                   
                   Note: This function uses geometric containment detection.
                   Some violations may not be detected due to complex geometries
                   or missing representations. Components that fail geometry
                   processing are skipped.
    
    Example:
        >>> guids = check_space_validation_inside('/path/to/model.ifc')
        >>> print(f"Found {len(guids)} violations")
    """
    # Validate input
    if not path_ifc_model:
        return []
    
    try:
        model = ifcopenshell.open(path_ifc_model)
    except Exception as e:
        logger.warning(f"Failed to open IFC model: {e}")
        return []
    
    # Get all spaces
    spaces = list(model.by_type('IfcSpace'))
    if not spaces:
        return []
    
    # Component types to check
    component_types = ['IfcWall', 'IfcCurtainWall', 'IfcColumn', 'IfcSlab', 'IfcRoof']
    
    # Collect all components
    components = []
    for comp_type in component_types:
        try:
            components.extend(model.by_type(comp_type))
        except Exception:
            pass
    
    if not components:
        return []
    
    # Settings for geometry creation
    settings = ifcopenshell.geom.settings()
    
    # Build meshes for spaces
    space_meshes = {}
    space_skipped = 0
    
    for space in spaces:
        try:
            shape = ifcopenshell.geom.create_shape(settings, space)
            verts = shape.geometry.verts
            faces = shape.geometry.faces
            
            # Reshape vertices: flat list -> (N, 3) array
            verts_array = np.array(verts, dtype=np.float32).reshape(-1, 3)
            faces_array = np.array(faces, dtype=np.int32).reshape(-1, 3)
            
            mesh = trimesh.Trimesh(vertices=verts_array, faces=faces_array)
            space_meshes[space.GlobalId] = mesh
        except Exception:
            space_skipped += 1
            continue
    
    if space_skipped > 0:
        logger.warning(f"Skipped {space_skipped}/{len(spaces)} spaces due to geometry errors")
    
    if not space_meshes:
        return []
    
    # Build meshes for components
    component_meshes = {}
    comp_skipped = 0
    
    for comp in components:
        try:
            shape = ifcopenshell.geom.create_shape(settings, comp)
            verts = shape.geometry.verts
            faces = shape.geometry.faces
            
            verts_array = np.array(verts, dtype=np.float32).reshape(-1, 3)
            faces_array = np.array(faces, dtype=np.int32).reshape(-1, 3)
            
            mesh = trimesh.Trimesh(vertices=verts_array, faces=faces_array)
            component_meshes[comp.GlobalId] = mesh
        except Exception:
            comp_skipped += 1
            continue
    
    if comp_skipped > 0:
        logger.warning(f"Skipped {comp_skipped}/{len(components)} components due to geometry errors")
    
    if not component_meshes:
        return []
    
    # Check each space for components inside
    violating_space_guids = []
    
    for space_guid, space_mesh in space_meshes.items():
        # Check if space mesh is valid for containment checks
        if not space_mesh.is_watertight:
            continue
        
        has_inside_component = False
        
        for comp_guid, comp_mesh in component_meshes.items():
            try:
                # Check if component bounding box is inside space bounding box first
                # This is a fast pre-filter
                bb_contains = trimesh.bounds.contains(space_mesh.bounds, comp_mesh.bounds)
                # bb_contains is an array, need all dimensions to be True
                if not np.all(bb_contains):
                    continue
                
                # Check if component is fully inside space
                # Sample points from component vertices
                sample_points = comp_mesh.vertices
                
                # Check if all vertices are inside the space
                is_inside = space_mesh.contains(sample_points)
                
                # If all vertices are inside, consider component inside
                if np.all(is_inside):
                    has_inside_component = True
                    break
                    
            except Exception:
                continue
        
        if has_inside_component:
            violating_space_guids.append(space_guid)
    
    return violating_space_guids