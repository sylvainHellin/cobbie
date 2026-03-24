import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.shape
import numpy as np
import trimesh
import shapely.geometry
from typing import List


def check_304_3_1_circular_space(path_ifc_model: str) -> List[str]:
    """
    Check if spaces have enough room for wheelchair turning space with minimum diameter of 1.52m.
    
    Rule 304.3.1 Circular Space: Circular space shall have a diameter of 1.52 m (60 inches) minimum.
    
    Applicable Space Classifications: Balcony, Circulation, Garage, Habitable, Institutional,
    Lobby, Mercantile, Office, Parking, Production, Refuge, Stair Hall, Workplace.
    
    Args:
        path_ifc_model: Path to the IFC model file.
        
    Returns:
        List of IFC GUIDs of spaces that violate the rule (diameter < 1.52m).
        
    Example:
        >>> violations = check_304_3_1_circular_space('/path/to/model.ifc')
        >>> print(f"Found {len(violations)} violations")
    """
    # Load model
    model = ifcopenshell.open(path_ifc_model)
    
    # Get all spaces
    spaces = model.by_type('IfcSpace')
    if not spaces:
        return []
    
    # Prepare spaces for classification
    spaces_data = [{"guid": s.GlobalId, "name": s.LongName or s.Name or ""} for s in spaces]
    
    # Classify spaces
    classified_spaces = classify_spaces(spaces_data, path_ifc_model)
    
    # Create lookup dictionary for classifications
    classification_map = {s['guid']: s['classification'] for s in classified_spaces}
    
    # Applicable classifications
    applicable_classifications = {
        'Balcony', 'Circulation', 'Garage', 'Habitable', 'Institutional',
        'Lobby', 'Mercantile', 'Office', 'Parking', 'Production',
        'Refuge', 'Stair Hall', 'Workplace'
    }
    
    # Minimum required diameter (1.52 m)
    min_required_diameter = 1.52
    
    violating_guids = []
    skipped = 0
    
    # Geometry settings
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    
    for space in spaces:
        guid = space.GlobalId
        
        # Skip spaces not in applicable classifications
        classification = classification_map.get(guid, 'Unclassified')
        if classification not in applicable_classifications:
            continue
        
        try:
            # Extract geometry
            shape = ifcopenshell.geom.create_shape(settings, space)
            verts = ifcopenshell.util.shape.get_vertices(shape.geometry)
            faces = ifcopenshell.util.shape.get_faces(shape.geometry)
            
            # Create trimesh
            mesh = trimesh.Trimesh(vertices=verts, faces=faces)
            
            # Get bounds to determine mid-height for horizontal section
            min_z, max_z = mesh.bounds[:, 2]
            
            # Skip if space has no height
            if max_z - min_z < 0.01:
                skipped += 1
                continue
            
            mid_z = (min_z + max_z) / 2
            
            # Get horizontal section
            section = mesh.section(plane_origin=[0, 0, mid_z], plane_normal=[0, 0, 1])
            
            if section is None:
                skipped += 1
                continue
            
            # Convert to 2D planar path
            path2d = section.to_planar()[0]
            polygons = path2d.polygons_full
            
            if not polygons:
                skipped += 1
                continue
            
            # Use the first polygon (main floor area)
            poly = polygons[0]
            
            # Calculate minimum bounding rectangle dimensions
            min_rect = poly.minimum_rotated_rectangle
            minx, miny, maxx, maxy = min_rect.bounds
            width = maxx - minx
            height = maxy - miny
            
            # Use the minimum dimension as an approximation of the largest possible diameter
            max_diameter = min(width, height)
            
            # Check violation
            if max_diameter < min_required_diameter:
                violating_guids.append(guid)
                
        except (AttributeError, RuntimeError, ValueError) as e:
            skipped += 1
            continue
    
    if skipped > 0:
        print(f"Warning: Skipped {skipped} spaces due to geometry processing issues")
    
    return violating_guids