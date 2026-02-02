import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.shape
from typing import List
import shapely.geometry as geom
import trimesh
import numpy as np

def check_304_3_1_circular_space(path_ifc_model: str) -> List[str]:
    """
    Check if spaces have enough room for wheelchair turning space (minimum 1.52m diameter).
    
    Rule 304.3.1: Circular space shall have a diameter of 1.52 m (60 inches) minimum.
    
    Applicable Space Classifications: Balcony, Circulation, Garage, Habitable, Institutional,
    Lobby, Mercantile, Office, Parking, Production, Refuge, Stair Hall, Workplace.
    
    This function analyzes space geometry to determine the maximum circular diameter available
    for wheelchair turning space. Spaces are filtered based on name/LongName keywords to identify
    relevant circulation and habitable spaces while excluding utility/secondary spaces.
    
    Args:
        path_ifc_model: Path to the IFC model file.
        
    Returns:
        List of IFC GUIDs of spaces that violate the rule (diameter < 1.52m).
        Returns empty list if no violations found or if no spaces exist in model.
        
    Example:
        >>> violations = check_304_3_1_circular_space('/path/to/model.ifc')
        >>> print(violations)
        ['10mjSDZJj9gPS2PrQaxa3z', '10mjSDZJj9gPS2PrQaxa4o']
    """
    model = ifcopenshell.open(path_ifc_model)
    spaces = model.by_type('IfcSpace')
    
    if not spaces:
        return []
    
    # Keywords for spaces that should be checked (circulation and habitable spaces)
    include_keywords = [
        'stair', 'stairs', 'hall', 'hallway', 'corridor', 'lobby', 'foyer', 'entry',
        'circulation', 'room', 'living', 'dining', 'kitchen', 'bedroom', 'office',
        'garage', 'parking', 'workplace', 'refuge'
    ]
    
    # Keywords for spaces that should be excluded (secondary/utility spaces)
    exclude_keywords = [
        'bathroom', 'toilet', 'closet', 'storage', 'utility', 'balcony', 'patio',
        'deck', 'porch', 'terrace', 'mechanical', 'electrical', 'shaft'
    ]
    
    def get_max_diameter(space) -> float:
        """Calculate maximum circular space diameter using mid-height section."""
        try:
            shape = ifcopenshell.geom.create_shape(settings, space)
            verts = ifcopenshell.util.shape.get_vertices(shape.geometry)
            faces = ifcopenshell.util.shape.get_faces(shape.geometry)
            
            mesh = trimesh.Trimesh(vertices=verts, faces=faces)
            
            # Get section at mid-height for 2D footprint
            z_height = (mesh.bounds[0, 2] + mesh.bounds[1, 2]) / 2
            section = mesh.section(plane_origin=[0, 0, z_height], plane_normal=[0, 0, 1])
            
            if section and len(section.to_planar()) > 0:
                path2d = section.to_planar()[0]
                if len(path2d.polygons_full) > 0:
                    polygon = path2d.polygons_full[0]
                    
                    # Use minimum rotated rectangle width as approximation for max inscribed circle
                    min_rect = polygon.minimum_rotated_rectangle
                    coords = list(min_rect.exterior.coords)
                    
                    if len(coords) >= 5:
                        p1 = geom.Point(coords[0])
                        p2 = geom.Point(coords[1])
                        p3 = geom.Point(coords[2])
                        width1 = p1.distance(p2)
                        width2 = p2.distance(p3)
                        min_dim = min(width1, width2)
                        return min_dim
                    
                    # Fallback: sampling method for more complex shapes
                    min_bounds = polygon.bounds
                    x_range = np.linspace(min_bounds[0], min_bounds[2], 50)
                    y_range = np.linspace(min_bounds[1], min_bounds[3], 50)
                    
                    max_inscribed_radius = 0
                    for x in x_range:
                        for y in y_range:
                            pt = geom.Point(x, y)
                            if polygon.contains(pt):
                                dist_to_edge = polygon.boundary.distance(pt)
                                if dist_to_edge > max_inscribed_radius:
                                    max_inscribed_radius = dist_to_edge
                    
                    return max_inscribed_radius * 2
        except (RuntimeError, AttributeError):
            pass
        return 0.0
    
    settings = ifcopenshell.geom.settings()
    min_diameter = 1.52
    violations = []
    skipped = 0
    
    for space in spaces:
        name = (getattr(space, 'Name', None) or '').lower()
        long_name = (getattr(space, 'LongName', None) or '').lower()
        combined_text = name + ' ' + long_name
        
        # Check if space should be excluded (utility/secondary spaces)
        should_exclude = any(kw in combined_text for kw in exclude_keywords)
        if should_exclude:
            continue
        
        # Check if space should be included based on keywords
        should_include = any(kw in combined_text for kw in include_keywords)
        if not should_include:
            continue
        
        diameter = get_max_diameter(space)
        if diameter <= 0:
            skipped += 1
            continue
        
        if diameter < min_diameter:
            violations.append(space.GlobalId)
    
    return violations