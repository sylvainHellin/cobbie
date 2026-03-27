import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.geom
import trimesh
import numpy as np
from typing import List


def check_504_2_stair_slab_connection(path_ifc_model: str) -> List[str]:
    """
    Rule 504.2: Check which stairs are not properly connected to slabs.
    
    All stairs shall be connected to slabs. This function identifies stairs
    that violate this rule by checking geometric connections between stair
    elements and external slab elements.
    
    Parameters:
    -----------
    path_ifc_model : str
        The file path to the IFC model.

    Returns:
    --------
    List[str]
        A list of IFC GUIDs of stair elements that violate the rule
        (i.e., stairs not properly connected to external slabs).
        Returns empty list if no violations are found.

    Example:
    -------
    >>> violations = check_504_2_stair_slab_connection('/path/to/model.ifc')
    >>> print(f"Found {len(violations)} stairs not connected to slabs")
    """
    def get_element_mesh(model, element):
        """Convert an IFC element to a trimesh object."""
        try:
            settings = ifcopenshell.geom.settings()
            settings.set('use-world-coords', True)
            shape = ifcopenshell.geom.create_shape(settings, element)
            
            verts = np.array(shape.geometry.verts).reshape(-1, 3)
            faces = np.array(shape.geometry.faces).reshape(-1, 3)
            
            return trimesh.Trimesh(vertices=verts, faces=faces)
        except Exception:
            return None
    
    def get_stair_mesh(model, stair):
        """Get mesh for a stair - either from its own representation or decomposed elements."""
        # First try to create mesh from the stair itself
        mesh = get_element_mesh(model, stair)
        if mesh is not None:
            return mesh
        
        # If that fails, try to create mesh from decomposed elements
        decomposed = ifcopenshell.util.element.get_decomposition(stair)
        if decomposed and len(decomposed) > 0:
            stair_meshes = []
            for elem in decomposed:
                elem_mesh = get_element_mesh(model, elem)
                if elem_mesh is not None:
                    stair_meshes.append(elem_mesh)
            
            if stair_meshes:
                return trimesh.util.concatenate(stair_meshes)
        
        return None
    
    # Open the model
    model = ifcopenshell.open(path_ifc_model)
    
    # Get all stairs and slabs
    stairs = model.by_type('IfcStair')
    slabs = model.by_type('IfcSlab')
    
    # Handle edge cases
    if not stairs:
        return []
    
    if not slabs:
        # No slabs in model - all stairs are violations
        return [s.GlobalId for s in stairs]
    
    violations = []
    tolerance = 0.1  # 10cm tolerance for connection
    skipped = 0
    
    for stair in stairs:
        # Get the stair mesh
        stair_mesh = get_stair_mesh(model, stair)
        
        if stair_mesh is None:
            skipped += 1
            violations.append(stair.GlobalId)
            continue
        
        # Get decomposed elements for this stair to filter out landing slabs
        decomposed = ifcopenshell.util.element.get_decomposition(stair)
        decomposed_set = set(decomposed) if decomposed else set()
        
        # Check connection to each external slab
        connected = False
        for slab in slabs:
            # Skip slabs that are part of this stair's decomposition (landing slabs)
            if slab in decomposed_set:
                continue
            
            slab_mesh = get_element_mesh(model, slab)
            if slab_mesh is None:
                continue
            
            # Check for intersection using boolean operations
            try:
                intersection = trimesh.boolean.intersection([stair_mesh, slab_mesh])
                if intersection and intersection.volume > 1e-6:
                    connected = True
                    break
            except Exception:
                pass
            
            # Check for proximity using closest_point
            try:
                closest, distances, _ = trimesh.proximity.closest_point(slab_mesh, stair_mesh.vertices)
                min_distance = np.min(distances)
                if min_distance < tolerance:
                    connected = True
                    break
            except Exception:
                pass
        
        if not connected:
            violations.append(stair.GlobalId)
    
    return violations