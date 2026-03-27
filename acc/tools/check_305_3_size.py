import ifcopenshell
import ifcopenshell.geom
import trimesh
import numpy as np
from shapely.geometry import Polygon, box
from shapely.affinity import translate, rotate
from typing import List, Optional


def check_305_3_size(path_ifc_model: str) -> List[str]:
    """
    Rule 305.3 Size: Check if spaces have inaccessible areas.
    
    The clear floor or ground space shall be 30 inches (760 mm) minimum 
    by 48 inches (1220 mm) minimum.
    
    Applicable Space Classifications: Balcony, Circulation, Garage, Habitable, 
    Institutional, Lobby, Mercantile, Office, Parking, Production, Refuge, 
    Stair Hall, Workplace
    
    Args:
        path_ifc_model: Path to the IFC model file
        
    Returns:
        List of IFC GUIDs of spaces that violate this rule (cannot accommodate
        a 760mm x 1220mm clear floor space)
        
    Example:
        >>> violations = check_305_3_size('model.ifc')
        >>> print(f"Found {len(violations)} violating spaces")
    """
    # Constants from the rule (in millimeters)
    MIN_WIDTH_MM = 760.0
    MIN_DEPTH_MM = 1220.0
    
    # Applicable space classifications
    APPLICABLE_CLASSIFICATIONS = {
        'Balcony', 'Circulation', 'Garage', 'Habitable', 'Institutional',
        'Lobby', 'Mercantile', 'Office', 'Parking', 'Production', 
        'Refuge', 'Stair Hall', 'Workplace'
    }
    
    # Open the IFC model
    model = ifcopenshell.open(path_ifc_model)
    
    # Get all spaces
    spaces = model.by_type('IfcSpace')
    if not spaces:
        return []
    
    # Prepare space data for classification
    space_data = []
    for space in spaces:
        space_data.append({
            "guid": space.GlobalId,
            "name": getattr(space, 'LongName', None) or getattr(space, 'Name', '')
        })
    
    # Classify spaces
    classified_spaces = classify_spaces(space_data, path_ifc_model)
    
    # Create a mapping from GUID to classification
    classification_map = {s['guid']: s['classification'] for s in classified_spaces}
    
    # Filter for applicable spaces
    applicable_spaces = []
    for space in spaces:
        classification = classification_map.get(space.GlobalId, 'Unclassified')
        if classification in APPLICABLE_CLASSIFICATIONS:
            applicable_spaces.append(space)
    
    if not applicable_spaces:
        return []
    
    violating_guids = []
    skipped_count = 0
    
    # Set up geometry settings
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    
    # Check each applicable space
    for space in applicable_spaces:
        try:
            # Extract geometry
            shape = ifcopenshell.geom.create_shape(settings, space)
            
            # Get vertices and faces
            verts = shape.geometry.verts
            faces = shape.geometry.faces
            
            if len(verts) == 0 or len(faces) == 0:
                skipped_count += 1
                continue
            
            # Create trimesh
            verts_array = np.array(verts).reshape(-1, 3)
            faces_array = np.array(faces).reshape(-1, 3)
            mesh = trimesh.Trimesh(vertices=verts_array, faces=faces_array)
            
            # Get 2D footprint via horizontal section
            z_level = (mesh.bounds[0, 2] + mesh.bounds[1, 2]) / 2
            section = mesh.section(plane_origin=[0, 0, z_level], plane_normal=[0, 0, 1])
            
            if section is None:
                skipped_count += 1
                continue
            
            path2d, transform = section.to_planar()
            
            if not hasattr(path2d, 'polygons_full') or len(path2d.polygons_full) == 0:
                skipped_count += 1
                continue
            
            polygon = path2d.polygons_full[0]
            
            # Check if polygon is valid
            if not polygon.is_valid or polygon.is_empty:
                skipped_count += 1
                continue
            
            # Convert dimensions to millimeters (assuming model is in meters)
            min_width = MIN_WIDTH_MM / 1000.0
            min_depth = MIN_DEPTH_MM / 1000.0
            
            # Check if rectangle can fit by testing multiple positions and rotations
            can_fit = _can_rectangle_fit(polygon, min_width, min_depth)
            
            if not can_fit:
                violating_guids.append(space.GlobalId)
                
        except (AttributeError, RuntimeError, ValueError) as e:
            skipped_count += 1
            continue
    
    if skipped_count > 0:
        print(f"Warning: Skipped {skipped_count} spaces due to geometry issues")
    
    return violating_guids


def _can_rectangle_fit(polygon: Polygon, width: float, depth: float) -> bool:
    """
    Check if a rectangle of given dimensions can fit inside a polygon.
    
    Tests multiple positions and rotations to determine if the rectangle
    can be placed entirely within the polygon.
    
    Args:
        polygon: The space footprint as a Shapely Polygon
        width: Rectangle width (in same units as polygon)
        depth: Rectangle depth (in same units as polygon)
        
    Returns:
        True if rectangle can fit, False otherwise
    """
    import math
    
    # Get polygon bounds
    minx, miny, maxx, maxy = polygon.bounds
    poly_width = maxx - minx
    poly_height = maxy - miny
    
    # Quick rejection: if bounding box is too small in both orientations
    if not ((poly_width >= width and poly_height >= depth) or 
            (poly_width >= depth and poly_height >= width)):
        return False
    
    # Create test rectangle at origin
    test_rect = box(0, 0, width, depth)
    
    # Check rotation from 0 to 90 degrees (every 5 degrees)
    for angle in np.linspace(0, 90, 19):
        # Rotate rectangle
        rotated_rect = rotate(test_rect, angle, origin='centroid', use_radians=False)
        
        # Get bounds of rotated rectangle
        rx_min, ry_min, rx_max, ry_max = rotated_rect.bounds
        rect_width = rx_max - rx_min
        rect_height = ry_max - ry_min
        
        # Sample positions on a grid within polygon bounds
        # Use smaller step for better accuracy
        step = min(width, depth) / 10.0
        
        for test_x in np.arange(minx - rx_min, maxx - rx_max + step, step):
            for test_y in np.arange(miny - ry_min, maxy - ry_max + step, step):
                # Translate test polygon
                translated = translate(rotated_rect, xoff=test_x, yoff=test_y)
                
                # Check containment
                if polygon.contains(translated):
                    return True
    
    return False