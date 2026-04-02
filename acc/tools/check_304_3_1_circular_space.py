import ifcopenshell
import ifcopenshell.geom
import numpy as np
import math
from typing import List
from shapely.geometry import Polygon
from scipy.spatial import ConvexHull

from src.tools.initial import classify_spaces


def check_304_3_1_circular_space(path_ifc_model: str) -> List[str]:
    """
    Check if spaces have sufficient room for wheelchair turning space with a minimum diameter of 1.52m.

    This function identifies spaces in the IFC model that do not meet the circular space
    requirement specified in rule 304.3.1. The rule requires that certain space classifications
    have a minimum diameter of 1.52m (60 inches) to accommodate wheelchair turning.

    Args:
        path_ifc_model: Path to the IFC model file.

    Returns:
        List of IFC GUIDs of spaces that violate the circular space requirement.
        Returns an empty list if no violations are found.

    Example:
        >>> violations = check_304_3_1_circular_space('/path/to/model.ifc')
        >>> print(f"Found {len(violations)} violations")
    """
    # Open the IFC model
    model = ifcopenshell.open(path_ifc_model)
    
    # Get all IfcSpace elements
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
    
    # Classify spaces using the CSV file
    classified_spaces = classify_spaces(space_data, path_ifc_model)
    
    # Create mapping from GUID to classification
    classification_map = {s['guid']: s['classification'] for s in classified_spaces}
    
    # Applicable space classifications per rule 304.3.1
    applicable_classifications = {
        'Balcony', 'Circulation', 'Garage', 'Habitable', 'Institutional',
        'Lobby', 'Mercantile', 'Office', 'Parking', 'Production',
        'Refuge', 'Stair Hall', 'Workplace'
    }
    
    # Minimum required diameter (in meters)
    MIN_DIAMETER = 1.52
    
    # Geometry settings for IFC processing
    settings = ifcopenshell.geom.settings()
    
    def calculate_minimum_width(polygon: Polygon) -> float:
        """
        Calculate the minimum width of a polygon using rotating calipers.
        
        This rotates the bounding box and finds the minimum dimension across all orientations,
        which represents the largest possible diameter that can fit in the space.
        
        Args:
            polygon: Shapely Polygon representing the space footprint.
            
        Returns:
            Minimum width (largest possible diameter) in meters.
        """
        if polygon.is_empty:
            return 0.0
        
        min_width = float('inf')
        
        # Sample rotations at 5-degree intervals
        for angle in range(0, 180, 5):
            rad = math.radians(angle)
            cos_a = math.cos(rad)
            sin_a = math.sin(rad)
            
            # Rotate all points
            rotated_points = []
            for x, y in polygon.exterior.coords:
                rx = x * cos_a - y * sin_a
                ry = x * sin_a + y * cos_a
                rotated_points.append((rx, ry))
            
            # Get bounding box dimensions
            xs = [p[0] for p in rotated_points]
            ys = [p[1] for p in rotated_points]
            width = max(xs) - min(xs)
            height = max(ys) - min(ys)
            
            # The minimum dimension gives the largest possible diameter
            min_dim = min(width, height)
            if min_dim < min_width:
                min_width = min_dim
        
        return min_width
    
    violations = []
    skipped = 0
    
    for space in spaces:
        guid = space.GlobalId
        classification = classification_map.get(guid, 'Unclassified')
        
        # Skip spaces not applicable to this rule
        if classification not in applicable_classifications:
            continue
        
        try:
            # Create geometry for the space
            shape = ifcopenshell.geom.create_shape(settings, space)
            verts = shape.geometry.verts
            
            # Convert to numpy array and extract 2D vertices (X, Y)
            verts_array = np.array(verts).reshape(-1, 3)
            verts_2d = verts_array[:, :2]
            
            # Create convex hull polygon for footprint estimation
            hull = ConvexHull(verts_2d)
            hull_vertices = [tuple(verts_2d[i]) for i in hull.vertices]
            polygon = Polygon(hull_vertices)
            
            # Calculate minimum width (largest possible diameter)
            min_width = calculate_minimum_width(polygon)
            
            # Check against minimum required diameter
            if min_width < MIN_DIAMETER:
                violations.append(guid)
                
        except (AttributeError, ValueError, RuntimeError) as e:
            # Skip spaces with geometry processing issues
            skipped += 1
            continue
    
    if skipped > 0:
        print(f"Warning: Skipped {skipped} spaces due to geometry processing errors")
    
    return violations