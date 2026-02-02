import ifcopenshell
import ifcopenshell.geom
import trimesh
import numpy as np
import shapely.geometry as geom
from typing import List


def check_304_3_1_circular_space(path_ifc_model: str) -> List[str]:
    """
    Rule: 304.3.1 304_3_1_circular_space
    Circular space shall have a diameter of 1.52 m (60 inches) minimum.
    
    Applicable Space Classifications: Balcony, Circulation, Garage, Habitable,
    Institutional, Lobby, Mercantile, Office, Parking, Production, Refuge,
    Stair Hall, Workplace
    
    Checks which spaces in the IFC model do not have enough room for wheelchair
    turning space with the required diameter.
    
    Args:
        path_ifc_model: Path to the IFC model file
        
    Returns:
        List of IFC GUIDs of all elements that violate this rule (spaces that
        don't have enough room for wheelchair turning space)
        
    Example:
        >>> violations = check_304_3_1_circular_space('/path/to/model.ifc')
        >>> print(f"Found {len(violations)} violations")
    """
    # Applicable classifications per rule
    APPLICABLE_CLASSIFICATIONS = {
        'Balcony', 'Circulation', 'Garage', 'Habitable', 'Institutional',
        'Lobby', 'Mercantile', 'Office', 'Parking', 'Production', 'Refuge',
        'Stair Hall', 'Workplace'
    }
    
    MIN_DIAMETER = 1.52  # meters
    
    def get_largest_circle_diameter(space) -> float:
        """Calculate the largest possible circle diameter that fits in a space's footprint."""
        try:
            settings = ifcopenshell.geom.settings()
            shape = ifcopenshell.geom.create_shape(settings, space)
            
            # Get vertices and faces
            verts = np.array(shape.geometry.verts).reshape(-1, 3)
            faces = shape.geometry.faces
            
            # Create mesh
            mesh = trimesh.Trimesh(vertices=verts, faces=faces)
            
            # Project vertices to XY plane (footprint)
            points_2d = [(v[0], v[1]) for v in verts]
            
            # Need at least 3 points to form a polygon
            if len(points_2d) < 3:
                return 0.0
            
            # Create a polygon from points using convex hull
            multi_point = geom.MultiPoint(points_2d)
            footprint = multi_point.convex_hull
            
            if footprint.is_empty:
                return 0.0
            
            # Get the minimum rotated rectangle (tightest fitting rectangle)
            min_rect = footprint.minimum_rotated_rectangle
            
            # Get the bounding box of the rotated rectangle
            minx, miny, maxx, maxy = min_rect.bounds
            width = maxx - minx
            height = maxy - miny
            
            # The largest circle diameter is the minimum dimension
            return min(width, height)
        except Exception:
            return 0.0
    
    # Open the IFC model
    model = ifcopenshell.open(path_ifc_model)
    
    # Get all spaces
    spaces = model.by_type('IfcSpace')
    if not spaces:
        return []
    
    # Prepare spaces for classification
    spaces_list = []
    for space in spaces:
        name = getattr(space, 'LongName', None) or getattr(space, 'Name', None) or ''
        spaces_list.append({
            'guid': space.GlobalId,
            'name': name,
            'space_obj': space  # Keep reference to original space object
        })
    
    # Classify spaces using the provided tool
    classified = classify_spaces(spaces_list, path_ifc_model)
    
    # Check for violations
    violations = []
    skipped = 0
    
    for space_info in classified:
        classification = space_info.get('classification', 'Unclassified')
        
        # Only check applicable classifications
        if classification not in APPLICABLE_CLASSIFICATIONS:
            continue
        
        # Calculate largest circle diameter
        space_obj = space_info['space_obj']
        diameter = get_largest_circle_diameter(space_obj)
        
        # Check if it meets the requirement
        if diameter > 0 and diameter < MIN_DIAMETER:
            violations.append(space_info['guid'])
        elif diameter == 0:
            skipped += 1
    
    if skipped > 0:
        print(f"Warning: Could not calculate diameter for {skipped} spaces")
    
    return violations