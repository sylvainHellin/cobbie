import ifcopenshell
import ifcopenshell.util.shape
import ifcopenshell.geom
import numpy as np
from typing import List, Dict, Tuple
from collections import Counter, defaultdict


def get_space_bottom_elevation(space, settings) -> float:
    """Extract the bottom elevation (min Z) of a space from its geometry."""
    try:
        shape = ifcopenshell.geom.create_shape(settings, space)
        # Get vertices (local coordinates)
        verts = shape.geometry.verts
        # Reshape to (N, 3)
        verts_array = np.array(verts).reshape(-1, 3)
        # Get transformation matrix
        matrix = ifcopenshell.util.shape.get_shape_matrix(shape)
        # Transform vertices to world coordinates
        ones = np.ones((verts_array.shape[0], 1))
        verts_homo = np.hstack([verts_array, ones])
        verts_world = (matrix @ verts_homo.T).T[:, :3]
        # Return min Z (bottom elevation)
        return np.min(verts_world[:, 2])
    except Exception as e:
        # If geometry extraction fails, return None
        return None


def check_spaces_same_storey_same_bottom_elevation(path_ifc_model: str) -> List[str]:
    """
    Rule: Spaces in Same Building Storey Must Have Same Bottom Elevation.
    
    Checks that all spaces within the same building storey have the same bottom
    elevation. Returns the GUIDs of spaces that violate this rule.
    
    Args:
        path_ifc_model: Path to the IFC model file.
        
    Returns:
        List of IFC GUIDs of spaces that violate the rule (i.e., belong to a storey
        where spaces have inconsistent bottom elevations).
        
    Example:
        >>> model_path = "/path/to/model.ifc"
        >>> violations = check_spaces_same_storey_same_bottom_elevation(model_path)
        >>> print(f"Found {len(violations)} violations")
    """
    model = ifcopenshell.open(path_ifc_model)
    
    # Get all spaces
    spaces = model.by_type("IfcSpace")
    if not spaces:
        return []
    
    # Build space to storey mapping using IfcRelAggregates
    space_to_storey = {}
    for rel in model.by_type('IfcRelAggregates'):
        if rel.RelatingObject.is_a('IfcBuildingStorey'):
            storey_guid = rel.RelatingObject.GlobalId
            for obj in rel.RelatedObjects:
                if obj.is_a('IfcSpace'):
                    space_to_storey[obj] = storey_guid
    
    if not space_to_storey:
        # No spaces found in any storey
        return []
    
    # Group spaces by storey with elevations
    settings = ifcopenshell.geom.settings()
    storey_spaces: Dict[str, List[Tuple]] = defaultdict(list)
    skipped = 0
    
    for space in spaces:
        storey_guid = space_to_storey.get(space)
        if storey_guid is None:
            continue
        
        elevation = get_space_bottom_elevation(space, settings)
        if elevation is None:
            skipped += 1
            continue
        
        storey_spaces[storey_guid].append((space, elevation))
    
    if skipped > 0:
        print(f"Warning: Could not extract geometry for {skipped} spaces")
    
    # Find violations: any storey with inconsistent elevations means ALL spaces in that storey violate
    violating_guids = []
    
    for space_list in storey_spaces.values():
        if len(space_list) < 2:
            # Not enough spaces to compare
            continue
        
        # Get unique elevations for this storey (rounded to handle floating point precision)
        unique_elevations = set(round(e, 2) for _, e in space_list)
        
        # If there are multiple unique elevations, flag all spaces in this storey
        if len(unique_elevations) > 1:
            for space, _ in space_list:
                violating_guids.append(space.GlobalId)
    
    return violating_guids