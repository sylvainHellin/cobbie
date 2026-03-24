import ifcopenshell
import ifcopenshell.geom
import trimesh
import numpy as np
from typing import List, Dict
import warnings
warnings.filterwarnings('ignore')

def check_space_validation_inside(path_ifc_model: str) -> List[str]:
    """
    Checks for components incorrectly inside spaces.
    
    This rule verifies that building components (Wall, CurtainWall, Column, Slab, Roof)
    are not incorrectly placed inside spaces. Components that are fully contained
    within a space volume indicate incorrect modeling.
    
    Args:
        path_ifc_model: Path to the IFC model file
        
    Returns:
        List of IFC GUIDs of spaces that have components incorrectly inside them.
        Returns empty list if no violations found or if model has no geometry.
        
    Example:
        >>> guids = check_space_validation_inside('model.ifc')
        >>> print(f"Found {len(guids)} spaces with violations")
    """
    model = ifcopenshell.open(path_ifc_model)
    
    # Get all spaces and relevant components
    spaces = list(model.by_type('IfcSpace'))
    relevant_types = ['IfcWall', 'IfcCurtainWall', 'IfcColumn', 'IfcSlab', 'IfcRoof']
    components = []
    for t in relevant_types:
        components.extend(model.by_type(t))
    
    if not spaces or not components:
        return []
    
    # Create ID-based lookup for elements we care about
    relevant_ids = set()
    for s in spaces:
        relevant_ids.add(s.id())
    for c in components:
        relevant_ids.add(c.id())
    
    # Set up geometry settings
    settings = ifcopenshell.geom.settings()
    
    # Build geometry map using element IDs
    id_to_element = {e.id(): e for e in spaces + components}
    element_meshes: Dict[int, trimesh.Trimesh] = {}
    skipped = 0
    
    iterator = ifcopenshell.geom.iterator(settings, model, 1)
    if iterator.initialize():
        while True:
            shape = iterator.get()
            elem_id = shape.id
            
            if elem_id in relevant_ids:
                try:
                    # Convert tuple to numpy array, then reshape
                    verts = np.array(shape.geometry.verts, dtype=np.float64).reshape(-1, 3)
                    faces = np.array(shape.geometry.faces, dtype=np.int32).reshape(-1, 3)
                    mesh = trimesh.Trimesh(vertices=verts, faces=faces)
                    
                    # Only keep meshes with reasonable geometry
                    if mesh.volume > 1e-10 or mesh.area > 1e-6:
                        element_meshes[elem_id] = mesh
                    else:
                        skipped += 1
                except Exception:
                    skipped += 1
            
            if not iterator.next():
                break
    
    if not element_meshes:
        return []
    
    if skipped > 0:
        print(f"Warning: Skipped {skipped} elements due to geometry issues")
    
    # Check for violations
    violating_space_guids = []
    tolerance = 0.03
    
    for space in spaces:
        if space.id() not in element_meshes:
            continue
        
        space_mesh = element_meshes[space.id()]
        space_bounds = space_mesh.bounds
        
        for comp in components:
            if comp.id() not in element_meshes:
                continue
            
            comp_mesh = element_meshes[comp.id()]
            comp_bounds = comp_mesh.bounds
            
            # Check if component is fully within space bounds (with tolerance)
            min_inside = (
                comp_bounds[0][0] >= space_bounds[0][0] + tolerance and
                comp_bounds[0][1] >= space_bounds[0][1] + tolerance and
                comp_bounds[0][2] >= space_bounds[0][2] + tolerance
            )
            
            max_inside = (
                comp_bounds[1][0] <= space_bounds[1][0] - tolerance and
                comp_bounds[1][1] <= space_bounds[1][1] - tolerance and
                comp_bounds[1][2] <= space_bounds[1][2] - tolerance
            )
            
            if min_inside and max_inside:
                # Component is fully inside space bounds - verify with sampling
                try:
                    # Sample vertices from component
                    verts = comp_mesh.vertices
                    
                    # Check a subset for efficiency
                    num_samples = min(len(verts), 100)
                    if len(verts) > num_samples:
                        indices = np.random.choice(len(verts), num_samples, replace=False)
                        sample_verts = verts[indices]
                    else:
                        sample_verts = verts
                    
                    # Check if samples are inside space
                    inside = space_mesh.contains(sample_verts)
                    inside_ratio = np.mean(inside)
                    
                    if inside_ratio > 0.5:
                        violating_space_guids.append(space.GlobalId)
                        break
                except Exception:
                    # Fallback to centroid check
                    try:
                        centroid = comp_mesh.center_mass
                        if space_mesh.contains([centroid])[0]:
                            violating_space_guids.append(space.GlobalId)
                            break
                    except Exception:
                        pass
    
    return violating_space_guids