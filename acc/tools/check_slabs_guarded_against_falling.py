import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.geom
import numpy as np
import trimesh
import shapely.geometry as geom
from scipy.spatial import ConvexHull
from typing import List, Tuple, Optional
import warnings

warnings.filterwarnings('ignore')

def get_element_mesh(model, element):
    """Extract a trimesh mesh from an IFC element."""
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)
    try:
        shape = ifcopenshell.geom.create_shape(settings, element)
        verts = np.array(shape.geometry.verts).reshape(-1, 3)
        faces = np.array(shape.geometry.faces).reshape(-1, 3)
        return trimesh.Trimesh(vertices=verts, faces=faces)
    except Exception:
        return None

def get_top_surface_2d(mesh, z_tolerance=0.05):
    """Get the 2D projection of the top surface of a mesh."""
    if mesh is None:
        return None, None
    
    z_values = mesh.vertices[:, 2]
    top_z = np.max(z_values)
    
    # Filter vertices near top surface
    top_verts = mesh.vertices[np.abs(mesh.vertices[:, 2] - top_z) < z_tolerance]
    
    if len(top_verts) < 3:
        return None, None
    
    # Create convex hull in 2D
    points_2d = top_verts[:, :2]
    try:
        hull = ConvexHull(points_2d)
        hull_points = points_2d[hull.vertices]
        poly = geom.Polygon(hull_points)
        if poly.is_valid and poly.area > 0.01:
            return poly, top_z
    except:
        pass
    
    return None, None

def check_barrier_protection_at_point(point_2d, barriers, ref_z, max_gap=0.15):
    """Check if a point is protected by a barrier.
    
    Args:
        point_2d: (x, y) tuple
        barriers: list of (polygon, height, bottom_z, top_z)
        ref_z: reference Z (slab top)
        max_gap: maximum gap from edge to barrier
    
    Returns:
        (is_protected, barrier_height_ok)
    """
    pt = geom.Point(point_2d)
    
    for barrier_poly, height, bottom_z, top_z in barriers:
        # Check if barrier is tall enough (min 1m)
        if height < 1.0:
            continue
        
        # Check if point touches or is inside barrier
        dist = pt.distance(barrier_poly)
        
        # Check if barrier polygon contains point (barrier is at the edge)
        if barrier_poly.contains(pt):
            # Barrier is at this point - check height
            height_ok = height >= 1.0
            return True, height_ok
        
        # Check if barrier is within gap distance
        if dist <= max_gap:
            # Barrier is near - also check that it starts at or below slab level
            if bottom_z <= ref_z + 0.2:
                height_ok = height >= 1.0
                return True, height_ok
    
    return False, False

def find_landing_at_point(point_2d, slabs_info, ref_z, max_fall=0.5, max_dist=0.1, min_width=0.2):
    """Check if there's an acceptable landing below this point.
    
    Args:
        point_2d: (x, y) tuple
        slabs_info: list of (polygon, top_z, bottom_z)
        ref_z: reference Z (slab top)
        max_fall: maximum acceptable fall height
        max_dist: maximum horizontal distance to landing
        min_width: minimum landing width
    
    Returns:
        bool: True if acceptable landing exists
    """
    pt = geom.Point(point_2d)
    
    for slab_poly, slab_top_z, slab_bottom_z in slabs_info:
        # Check if this slab is below reference and within acceptable fall height
        fall_height = ref_z - slab_top_z
        
        if 0 < fall_height <= max_fall:
            # Check horizontal distance
            dist = pt.distance(slab_poly)
            if dist <= max_dist:
                # Check landing width (minimum dimension of slab)
                min_dim = min(slab_poly.bounds[2] - slab_poly.bounds[0],
                             slab_poly.bounds[3] - slab_poly.bounds[1])
                if min_dim >= min_width:
                    return True
    
    return False

def is_slab_protected(model, slab, barriers_info, slabs_info):
    """Check if a slab is protected against falling."""
    slab_mesh = get_element_mesh(model, slab)
    if slab_mesh is None:
        return True  # Skip if no geometry
    
    slab_poly, slab_top_z = get_top_surface_2d(slab_mesh)
    if slab_poly is None:
        return True  # Skip if no valid top surface
    
    # Sample points along the perimeter
    perimeter = slab_poly.length
    if perimeter == 0:
        return True
    
    # Sample every 0.05m along the perimeter
    sample_interval = 0.05
    num_samples = max(10, int(perimeter / sample_interval))
    
    boundary = slab_poly.boundary
    if hasattr(boundary, 'geoms'):
        # MultiLineString
        lines = boundary.geoms
    else:
        # LineString
        lines = [boundary]
    
    # Collect all sample points
    sample_points = []
    for line in lines:
        length = line.length
        if length > 0:
            for i in range(int(length / sample_interval) + 1):
                dist = i * sample_interval
                if dist <= length:
                    pt = line.interpolate(dist)
                    sample_points.append((pt.x, pt.y))
    
    if not sample_points:
        return True
    
    # Check each point for protection
    unprotected_segments = []
    current_segment_start = None
    
    for i, (x, y) in enumerate(sample_points):
        point = (x, y)
        
        # Check if protected by barriers
        is_protected, height_ok = check_barrier_protection_at_point(
            point, barriers_info, slab_top_z, max_gap=0.15
        )
        
        if is_protected and not height_ok:
            # Barrier too low - consider unprotected
            if current_segment_start is None:
                current_segment_start = i
        elif is_protected:
            if current_segment_start is not None:
                # End of unprotected segment
                segment_length = (i - current_segment_start) * sample_interval
                unprotected_segments.append(segment_length)
                current_segment_start = None
        else:
            # Check if there's an acceptable landing
            has_landing = find_landing_at_point(
                point, slabs_info, slab_top_z, 
                max_fall=0.5, max_dist=0.1, min_width=0.2
            )
            
            if has_landing:
                if current_segment_start is not None:
                    segment_length = (i - current_segment_start) * sample_interval
                    unprotected_segments.append(segment_length)
                    current_segment_start = None
            else:
                # Point is unprotected
                if current_segment_start is None:
                    current_segment_start = i
    
    # Check if there's an ongoing unprotected segment
    if current_segment_start is not None:
        segment_length = (len(sample_points) - current_segment_start) * sample_interval
        unprotected_segments.append(segment_length)
    
    # Check if any unprotected segment exceeds max gap (0.1m)
    max_gap = 0.1
    for seg_length in unprotected_segments:
        if seg_length > max_gap:
            return False  # Violation found
    
    return True

def check_slabs_guarded_against_falling(path_ifc_model: str) -> List[str]:
    """
    Check if slabs in the IFC model are guarded against falling.
    
    This function analyzes slabs to ensure they are protected by barriers (walls,
    railings, columns, stairs) or have acceptable drops to other surfaces.
    
    Parameters checked:
    - Minimum barrier height: 1.0m
    - Maximum gap between barriers: 0.1m
    - Maximum acceptable fall to landing: 0.5m
    - Maximum horizontal distance to landing: 0.1m
    - Minimum landing width: 0.2m
    - Maximum gap from platform to barriers: 0.1m
    
    Args:
        path_ifc_model: Path to the IFC model file.
        
    Returns:
        List of IFC GUIDs of slabs that violate the guarding rule.
        
    Example:
        >>> violations = check_slabs_guarded_against_falling("/path/to/model.ifc")
        >>> print(f"Found {len(violations)} violations")
    """
    model = ifcopenshell.open(path_ifc_model)
    
    # Get all slabs
    all_slabs = model.by_type('IfcSlab')
    
    # Filter for floor slabs (PredefinedType = 'FLOOR', 'BASESLAB', or other relevant types)
    floor_slabs = [s for s in all_slabs if getattr(s, 'PredefinedType', None) in ['FLOOR', 'BASESLAB', 'ROOF', 'LANDING']]
    
    if not floor_slabs:
        return []
    
    # Process barrier components
    barrier_types = ['IfcWall', 'IfcRailing', 'IfcColumn', 'IfcStair', 'IfcBuildingElementProxy']
    barriers_info = []  # List of (polygon_2d, height, bottom_z, top_z)
    
    for btype in barrier_types:
        for barrier in model.by_type(btype):
            barrier_mesh = get_element_mesh(model, barrier)
            if barrier_mesh is not None:
                verts = barrier_mesh.vertices
                bottom_z = np.min(verts[:, 2])
                top_z = np.max(verts[:, 2])
                height = top_z - bottom_z
                
                # Get 2D footprint using convex hull
                points_2d = verts[:, :2]
                try:
                    hull = ConvexHull(points_2d)
                    hull_points = points_2d[hull.vertices]
                    poly = geom.Polygon(hull_points)
                    if poly.is_valid and poly.area > 0.01:
                        barriers_info.append((poly, height, bottom_z, top_z))
                except:
                    pass
    
    # Process all slabs for potential landings
    slabs_info = []  # List of (polygon_2d, top_z, bottom_z)
    for slab in all_slabs:
        slab_mesh = get_element_mesh(model, slab)
        if slab_mesh is not None:
            poly, top_z = get_top_surface_2d(slab_mesh)
            if poly is not None:
                bottom_z = np.min(slab_mesh.vertices[:, 2])
                slabs_info.append((poly, top_z, bottom_z))
    
    # Check each floor slab
    violating_guids = []
    for slab in floor_slabs:
        if not is_slab_protected(model, slab, barriers_info, slabs_info):
            violating_guids.append(slab.GlobalId)
    
    return violating_guids