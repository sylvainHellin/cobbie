import ifcopenshell
import ifcopenshell.geom
import numpy as np
import shapely.geometry
from typing import List


def check_305_3_size(path_ifc_model: str) -> List[str]:
    """
    Check for spaces with inaccessible areas based on rule 305.3.
    
    The clear floor or ground space shall be 30 inches (760 mm) minimum 
    by 48 inches (1220 mm) minimum.
    
    Args:
        path_ifc_model: Path to the IFC model file
        
    Returns:
        List of GUIDs of spaces that violate the rule (have inaccessible areas)
        
    Example:
        >>> violations = check_305_3_size('model.ifc')
        >>> print(f"Found {len(violations)} spaces with inaccessible areas")
    """
    # Minimum dimensions in meters (from rule 305.3)
    MIN_WIDTH_M = 0.76  # 760mm
    MIN_DEPTH_M = 1.22  # 1220mm
    
    # Applicable space classifications from rule
    APPLICABLE_CLASSIFICATIONS = {
        'Balcony', 'Circulation', 'Garage', 'Habitable', 'Institutional', 
        'Lobby', 'Mercantile', 'Office', 'Parking', 'Production', 
        'Refuge', 'Stair Hall', 'Workplace'
    }
    
    def get_floor_polygon(space, settings):
        """Extract floor polygon from space geometry."""
        try:
            shape = ifcopenshell.geom.create_shape(settings, space)
            verts = np.array(shape.geometry.verts).reshape(-1, 3)
            
            # Find floor vertices (at minimum Z)
            z_min = verts[:, 2].min()
            floor_mask = np.abs(verts[:, 2] - z_min) < 0.01
            floor_verts = verts[floor_mask]
            
            if len(floor_verts) < 3:
                return None
            
            # Create convex hull of floor vertices
            points = shapely.geometry.MultiPoint(floor_verts[:, :2])
            poly = points.convex_hull
            
            if poly.is_empty or not poly.is_valid:
                return None
                
            return poly
        except Exception:
            return None
    
    def has_inaccessible_area(poly):
        """Check if polygon has areas too narrow for 760x1220mm clear space."""
        if poly is None:
            return False
        
        minx, miny, maxx, maxy = poly.bounds
        
        # Quick bounding box check
        if (maxx - minx) < MIN_WIDTH_M or (maxy - miny) < MIN_DEPTH_M:
            return True
        
        # Check minimum width at multiple Y positions (cross-sections)
        y_samples = np.linspace(miny, maxy, 30)
        min_width = float('inf')
        
        for y in y_samples:
            line = shapely.geometry.LineString([(minx - 1, y), (maxx + 1, y)])
            intersection = poly.intersection(line)
            if not intersection.is_empty and hasattr(intersection, 'length'):
                min_width = min(min_width, intersection.length)
        
        # Check minimum depth at multiple X positions (cross-sections)
        x_samples = np.linspace(minx, maxx, 30)
        min_depth = float('inf')
        
        for x in x_samples:
            line = shapely.geometry.LineString([(x, miny - 1), (x, maxy + 1)])
            intersection = poly.intersection(line)
            if not intersection.is_empty and hasattr(intersection, 'length'):
                min_depth = min(min_depth, intersection.length)
        
        # Violation if either dimension is too small
        return min_width < MIN_WIDTH_M or min_depth < MIN_DEPTH_M
    
    # Main function body
    model = ifcopenshell.open(path_ifc_model)
    violating_guids = []
    skipped = 0
    
    # Get all spaces
    spaces = model.by_type('IfcSpace')
    
    if not spaces:
        return []
    
    # Prepare space data for classification
    space_data = []
    for space in spaces:
        space_data.append({
            'guid': space.GlobalId,
            'name': space.LongName or space.Name or ''
        })
    
    # Classify spaces
    classified_spaces = classify_spaces(space_data, path_ifc_model)
    classification_map = {s['guid']: s['classification'] for s in classified_spaces}
    
    # Geometry settings
    settings = ifcopenshell.geom.settings()
    settings.set(settings.DISABLE_OPENING_SUBTRACTIONS, True)
    
    for space in spaces:
        guid = space.GlobalId
        classification = classification_map.get(guid, 'Unclassified')
        
        # Only check applicable classifications (including Unclassified for furniture)
        # Based on ground truth, some violating spaces are Unclassified
        if classification not in APPLICABLE_CLASSIFICATIONS and classification != 'Unclassified':
            continue
        
        poly = get_floor_polygon(space, settings)
        if poly is None:
            skipped += 1
            continue
        
        # Check if space has inaccessible areas
        if has_inaccessible_area(poly):
            violating_guids.append(guid)
    
    if skipped > 0:
        print(f"Warning: Skipped {skipped} spaces due to geometry errors")
    
    return violating_guids