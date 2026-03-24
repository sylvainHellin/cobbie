import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.geom
import trimesh
import shapely.geometry as geom
from shapely.geometry import MultiPoint, box
import numpy as np
from typing import List, Optional
import warnings

warnings.filterwarnings('ignore')

def get_element_footprint(element) -> Optional[geom.Polygon]:
    """Extract 2D footprint from an element."""
    try:
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        
        shape = ifcopenshell.geom.create_shape(settings, element)
        verts = shape.geometry.verts
        
        verts_array = np.array(verts).reshape(-1, 3)
        
        # Try horizontal slice first for spaces
        try:
            mesh = trimesh.Trimesh(vertices=verts_array, faces=shape.geometry.faces)
            bounds = mesh.bounds
            z_min, z_max = bounds[0, 2], bounds[1, 2]
            z_mid = (z_min + z_max) / 2
            
            section = mesh.section(plane_origin=[0, 0, z_mid], plane_normal=[0, 0, 1])
            if section:
                path2d = section.to_planar()[0]
                if path2d.polygons_full:
                    return path2d.polygons_full[0]
        except:
            pass
        
        # Fall back to bounding box for furniture or if slice fails
        minx, miny, maxx, maxy = verts_array[:, 0].min(), verts_array[:, 1].min(), verts_array[:, 0].max(), verts_array[:, 1].max()
        return box(minx, miny, maxx, maxy)
        
    except Exception:
        return None

def get_element_centroid(element) -> Optional[geom.Point]:
    """Get the 2D centroid of an element."""
    try:
        settings = ifcopenshell.geom.settings()
        settings.set(settings.USE_WORLD_COORDS, True)
        
        shape = ifcopenshell.geom.create_shape(settings, element)
        verts = shape.geometry.verts
        
        verts_array = np.array(verts).reshape(-1, 3)
        cx = np.mean(verts_array[:, 0])
        cy = np.mean(verts_array[:, 1])
        
        return geom.Point(cx, cy)
    except Exception:
        return None

def can_fit_rectangle_with_obstructions(space_footprint: geom.Polygon, obstruction_polygons: List[geom.Polygon], width: float, depth: float) -> bool:
    """Check if a rectangle can fit in space avoiding obstructions."""
    if not space_footprint.is_valid:
        space_footprint = space_footprint.buffer(0)
        if space_footprint.is_empty or not space_footprint.is_valid:
            return False
    
    minx, miny, maxx, maxy = space_footprint.bounds
    poly_width = maxx - minx
    poly_depth = maxy - miny
    
    # Quick bounds check
    if not ((poly_width >= width and poly_depth >= depth) or (poly_width >= depth and poly_depth >= width)):
        return False
    
    # Combine obstructions
    if obstruction_polygons:
        combined_obstructions = geom.MultiPolygon(obstruction_polygons)
    else:
        combined_obstructions = None
    
    # Test multiple orientations
    orientations = [0, 90, 45, 30, 60]
    
    for angle_deg in orientations:
        angle_rad = np.radians(angle_deg)
        cos_a, sin_a = np.cos(angle_rad), np.sin(angle_rad)
        
        # Test at centroid
        test_points = [space_footprint.centroid]
        
        # Test at additional interior points
        for _ in range(20):
            x = np.random.uniform(minx, maxx)
            y = np.random.uniform(miny, maxy)
            pt = geom.Point(x, y)
            if space_footprint.contains(pt):
                test_points.append(pt)
        
        for center in test_points:
            cx, cy = center.x, center.y
            
            corners_local = [
                (-width/2, -depth/2), (width/2, -depth/2),
                (width/2, depth/2), (-width/2, depth/2)
            ]
            
            corners_rotated = []
            for x, y in corners_local:
                xr = x * cos_a - y * sin_a
                yr = x * sin_a + y * cos_a
                corners_rotated.append((cx + xr, cy + yr))
            
            rect = geom.Polygon(corners_rotated)
            
            if not rect.is_valid:
                continue
            
            if space_footprint.contains(rect):
                if combined_obstructions is None or not rect.intersects(combined_obstructions):
                    return True
    
    return False

def check_305_3_size(path_ifc_model: str) -> List[str]:
    """
    Check if spaces have accessible clear floor space per rule 305.3.
    
    Rule: 305.3 Size
    The clear floor or ground space shall be 30 inches (760 mm) minimum 
    by 48 inches (1220 mm) minimum.
    
    Parameters: Applicable Space Classifications: Balcony, Circulation, Garage, 
    Habitable, Institutional, Lobby, Mercantile, Office, Parking, Production, 
    Refuge, Stair Hall, Workplace
    
    Args:
        path_ifc_model: Path to the IFC model file.
        
    Returns:
        List of IFC GUIDs of elements that violate the rule (furniture elements
        in spaces that cannot accommodate a 760mm x 1220mm clear floor area).
        Returns one representative GUID per inaccessible space.
    """
    model = ifcopenshell.open(path_ifc_model)
    spaces = model.by_type('IfcSpace')
    
    if not spaces:
        return []
    
    # Classify spaces
    space_dicts = [{'guid': s.GlobalId, 'name': s.LongName or s.Name or ''} for s in spaces]
    classified_spaces = classify_spaces(space_dicts, path_ifc_model)
    
    applicable_classifications = {
        'Balcony', 'Circulation', 'Garage', 'Habitable', 'Institutional',
        'Lobby', 'Mercantile', 'Office', 'Parking', 'Production',
        'Refuge', 'Stair Hall', 'Workplace'
    }
    
    violating_guids = []
    min_width = 760  # mm
    min_depth = 1220  # mm
    
    # Get all furnishing elements
    furniture_elements = model.by_type('IfcFurnishingElement')
    
    # Build index: furniture GUID -> footprint, centroid
    furniture_index = {}
    for furn in furniture_elements:
        footprint = get_element_footprint(furn)
        centroid = get_element_centroid(furn)
        if footprint and centroid:
            furniture_index[furn.GlobalId] = {
                'element': furn,
                'footprint': footprint,
                'centroid': centroid
            }
    
    # Check each applicable space
    for i, space in enumerate(spaces):
        classification = classified_spaces[i].get('classification', 'Unclassified')
        
        if classification not in applicable_classifications:
            continue
        
        space_footprint = get_element_footprint(space)
        if space_footprint is None:
            continue
        
        # Find furniture geometrically contained in this space
        space_furniture = []
        for furn_guid, furn_data in furniture_index.items():
            if space_footprint.contains(furn_data['centroid']):
                space_furniture.append(furn_data)
        
        # Check if space can accommodate the required rectangle
        obstruction_polygons = [f['footprint'] for f in space_furniture]
        
        if not can_fit_rectangle_with_obstructions(space_footprint, obstruction_polygons, min_width, min_depth):
            # Space is inaccessible - add one representative furniture GUID
            if space_furniture:
                violating_guids.append(space_furniture[0]['element'].GlobalId)
    
    return list(dict.fromkeys(violating_guids))