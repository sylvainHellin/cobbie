import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.shape
import numpy as np
import trimesh
from shapely.geometry import Polygon
from typing import List
import sys


def check_305_3_size(path_ifc_model: str) -> List[str]:
    """
    Check if spaces violate rule 305.3 Size - minimum clear floor space of 760mm x 1220mm.
    
    Rule 305.3 requires that the clear floor or ground space shall be 30 inches (760 mm) 
    minimum by 48 inches (1220 mm) minimum. This function checks if a space can accommodate
    this minimum rectangle anywhere within its floor area.
    
    Parameters:
    - Applicable Space Classifications: Balcony, Circulation, Garage, Habitable, Institutional, 
      Lobby, Mercantile, Office, Parking, Production, Refuge, Stair Hall, Workplace
    
    Args:
        path_ifc_model: Path to the IFC model file.
        
    Returns:
        List of IFC GUIDs of spaces that violate the rule (have inaccessible areas
        where the required 760x1220mm rectangle cannot fit).
        
    Example:
        >>> guids = check_305_3_size('/path/to/model.ifc')
        >>> print(f"Found {len(guids)} violating spaces")
    """
    # Import classify_spaces for space classification
    try:
        from src.tools.initial import classify_spaces
    except ImportError:
        # Fallback if not in expected environment
        classify_spaces = None
    
    # Required dimensions in meters
    min_width = 0.760  # 760 mm
    min_length = 1.220  # 1220 mm
    
    # Applicable space classifications per the rule
    applicable_classifications = {
        'Balcony', 'Circulation', 'Garage', 'Habitable', 'Institutional',
        'Lobby', 'Mercantile', 'Office', 'Parking', 'Production', 
        'Refuge', 'Stair Hall', 'Workplace'
    }
    
    violating_guids = []
    
    try:
        model = ifcopenshell.open(path_ifc_model)
    except Exception as e:
        print(f"Error opening IFC model: {e}")
        return []
    
    # Get all spaces
    spaces = model.by_type('IfcSpace')
    if not spaces:
        return []
    
    # Prepare space data for classification
    space_data = []
    for space in spaces:
        name = getattr(space, 'LongName', None) or getattr(space, 'Name', '') or ''
        space_data.append({
            'guid': space.GlobalId,
            'name': name
        })
    
    # Classify spaces
    space_classification = {}
    if classify_spaces is not None:
        try:
            classified_spaces = classify_spaces(space_data, path_ifc_model)
            space_classification = {s['guid']: s.get('classification', 'Unclassified') 
                                   for s in classified_spaces}
        except Exception as e:
            print(f"Warning: Could not classify spaces: {e}")
    
    # Settings for geometry creation
    settings = ifcopenshell.geom.settings()
    
    skipped = 0
    
    for space in spaces:
        try:
            # Check if space is of applicable classification
            classification = space_classification.get(space.GlobalId, 'Unclassified')
            if classification not in applicable_classifications:
                continue
            
            # Get shape geometry
            shape = ifcopenshell.geom.create_shape(settings, space)
            
            # Get vertices, faces, and matrix using utility functions
            verts = ifcopenshell.util.shape.get_vertices(shape.geometry)
            faces = ifcopenshell.util.shape.get_faces(shape.geometry)
            matrix = ifcopenshell.util.shape.get_shape_matrix(shape)
            
            # Transform vertices to world coordinates
            verts_transformed = verts @ matrix[:3, :3].T + matrix[:3, 3]
            
            # Create trimesh
            mesh = trimesh.Trimesh(vertices=verts_transformed, faces=faces)
            
            # Get horizontal section at mid-height
            z_min = mesh.bounds[0, 2]
            z_max = mesh.bounds[1, 2]
            z_mid = (z_min + z_max) / 2
            
            section = mesh.section(plane_origin=[0, 0, z_mid], plane_normal=[0, 0, 1])
            
            if section and section.to_planar():
                path2d, _ = section.to_planar()
                if path2d.polygons_full:
                    # Get the largest polygon (main space footprint)
                    main_poly = max(path2d.polygons_full, key=lambda p: p.area)
                    
                    if not main_poly.is_valid or main_poly.is_empty:
                        continue
                    
                    # Check if the required rectangle can fit anywhere in the polygon
                    # using grid search
                    minx, miny, maxx, maxy = main_poly.bounds
                    
                    # Quick bounding box check
                    bbox_width = maxx - minx
                    bbox_length = maxy - miny
                    
                    # If bounding box is too small, it's definitely a violation
                    if bbox_width < min_width or bbox_length < min_width:
                        violating_guids.append(space.GlobalId)
                        continue
                    
                    # Grid search to find if rectangle can fit anywhere
                    step = 0.1  # 10cm resolution
                    fits = False
                    
                    # Try both orientations of the rectangle
                    for x in np.arange(minx, maxx - min_width + step, step):
                        for y in np.arange(miny, maxy - min_length + step, step):
                            # Test orientation 1: width x length
                            rect1 = Polygon([
                                (x, y),
                                (x + min_width, y),
                                (x + min_width, y + min_length),
                                (x, y + min_length)
                            ])
                            
                            if main_poly.contains(rect1):
                                fits = True
                                break
                            
                            # Test orientation 2: length x width
                            rect2 = Polygon([
                                (x, y),
                                (x + min_length, y),
                                (x + min_length, y + min_width),
                                (x, y + min_width)
                            ])
                            
                            if main_poly.contains(rect2):
                                fits = True
                                break
                        
                        if fits:
                            break
                    
                    # If rectangle cannot fit anywhere, it's a violation
                    if not fits:
                        violating_guids.append(space.GlobalId)
        
        except Exception as e:
            skipped += 1
            continue
    
    if skipped > 0:
        print(f"Warning: Skipped {skipped} spaces due to processing errors")
    
    return violating_guids