import ifcopenshell
import ifcopenshell.geom
import numpy as np
import trimesh
from typing import List, Optional, Dict, Tuple


def get_element_mesh(element, settings) -> Optional[trimesh.Trimesh]:
    """Get trimesh object from IFC element"""
    try:
        shape = ifcopenshell.geom.create_shape(settings, element)
        verts = shape.geometry.verts
        faces = shape.geometry.faces
        verts_array = np.array(verts).reshape(-1, 3)
        faces_array = np.array(faces).reshape(-1, 3)
        return trimesh.Trimesh(vertices=verts_array, faces=faces_array)
    except Exception:
        return None


def create_spatial_hash(elements_with_bounds: List[Tuple], grid_size: float) -> Dict[Tuple[int, int, int], List[int]]:
    """Create a spatial hash grid for fast AABB overlap queries"""
    spatial_hash = {}
    for idx, (bounds_min, bounds_max) in enumerate(elements_with_bounds):
        # Get grid cells that the element's AABB touches
        min_cell = tuple(np.floor(bounds_min / grid_size).astype(int))
        max_cell = tuple(np.ceil(bounds_max / grid_size).astype(int))
        
        # Add element index to all cells it touches
        for x in range(min_cell[0], max_cell[0] + 1):
            for y in range(min_cell[1], max_cell[1] + 1):
                for z in range(min_cell[2], max_cell[2] + 1):
                    cell_key = (x, y, z)
                    if cell_key not in spatial_hash:
                        spatial_hash[cell_key] = []
                    spatial_hash[cell_key].append(idx)
    
    return spatial_hash


def get_overlapping_indices(query_min: np.ndarray, query_max: np.ndarray, 
                            spatial_hash: Dict, grid_size: float) -> set:
    """Get all element indices that might overlap with query AABB"""
    min_cell = tuple(np.floor(query_min / grid_size).astype(int))
    max_cell = tuple(np.ceil(query_max / grid_size).astype(int))
    
    overlapping = set()
    for x in range(min_cell[0], max_cell[0] + 1):
        for y in range(min_cell[1], max_cell[1] + 1):
            for z in range(min_cell[2], max_cell[2] + 1):
                cell_key = (x, y, z)
                if cell_key in spatial_hash:
                    overlapping.update(spatial_hash[cell_key])
    
    return overlapping


def check_space_validation_inside(path_ifc_model: str) -> List[str]:
    """
    Check for components incorrectly inside spaces.
    
    This rule identifies structural elements (Wall, CurtainWall, Column, Slab, Roof)
    that are fully contained within a space volume, which indicates modeling errors.
    
    Args:
        path_ifc_model: Path to the IFC model file.
        
    Returns:
        List of IFC GUIDs of spaces that have components incorrectly inside them.
        
    Example:
        >>> guids = check_space_validation_inside('/path/to/model.ifc')
        >>> print(f"Found {len(guids)} spaces with invalid components")
    """
    model = ifcopenshell.open(path_ifc_model)
    
    # Settings for geometry
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    
    # Component types to check
    component_types = {'IfcWall', 'IfcCurtainWall', 'IfcColumn', 'IfcSlab', 'IfcRoof'}
    
    # Collect all components and build their meshes
    component_data = []  # list of dicts with element, mesh, bounds
    skipped_components = 0
    
    for comp_type in component_types:
        for comp in model.by_type(comp_type):
            mesh = get_element_mesh(comp, settings)
            if mesh is None:
                skipped_components += 1
                continue
            
            bounds = mesh.bounds
            component_data.append({
                'element': comp,
                'mesh': mesh,
                'bounds_min': bounds[0],
                'bounds_max': bounds[1]
            })
    
    if not component_data:
        return []
    
    # Build spatial hash for components
    all_bounds = [(c['bounds_min'], c['bounds_max']) for c in component_data]
    all_mins = np.array([b[0] for b in all_bounds])
    all_maxs = np.array([b[1] for b in all_bounds])
    model_extent = np.max(all_maxs - all_mins)
    grid_size = model_extent / 50  # Adaptive grid size
    
    spatial_hash = create_spatial_hash(all_bounds, grid_size)
    
    violating_space_guids = []
    skipped_spaces = 0
    
    for space in model.by_type('IfcSpace'):
        try:
            # Build space mesh
            space_mesh = get_element_mesh(space, settings)
            if space_mesh is None or not space_mesh.is_watertight:
                skipped_spaces += 1
                continue
            
            space_bounds = space_mesh.bounds
            space_min, space_max = space_bounds[0], space_bounds[1]
            
            # Use spatial hash to get potentially overlapping components
            candidate_indices = get_overlapping_indices(space_min, space_max, spatial_hash, grid_size)
            
            if not candidate_indices:
                continue
            
            # Check each candidate
            for idx in candidate_indices:
                comp_data = component_data[idx]
                comp_min = comp_data['bounds_min']
                comp_max = comp_data['bounds_max']
                
                # Precise AABB overlap check
                overlap = not (
                    comp_max[0] < space_min[0] or comp_min[0] > space_max[0] or
                    comp_max[1] < space_min[1] or comp_min[1] > space_max[1] or
                    comp_max[2] < space_min[2] or comp_min[2] > space_max[2]
                )
                
                if not overlap:
                    continue
                
                # Precise check: is component fully inside space?
                # Component is inside if ALL its vertices are inside the space
                inside = space_mesh.contains(comp_data['mesh'].vertices)
                
                if np.all(inside):
                    violating_space_guids.append(space.GlobalId)
                    break  # Found a violation, move to next space
        
        except Exception:
            skipped_spaces += 1
            continue
    
    return list(set(violating_space_guids))
