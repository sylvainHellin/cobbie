import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.shape
import trimesh
import numpy as np
import shapely.geometry as sg
from typing import List, Dict, Tuple, Optional


def create_trimesh_from_element(element, settings):
    """Create a trimesh object from an IFC element."""
    try:
        shape = ifcopenshell.geom.create_shape(settings, element)
        verts = ifcopenshell.util.shape.get_vertices(shape.geometry)
        faces = ifcopenshell.util.shape.get_faces(shape.geometry)
        matrix = ifcopenshell.util.shape.get_shape_matrix(shape)
        verts_world = np.dot(verts, matrix[:3, :3].T) + matrix[:3, 3]
        return trimesh.Trimesh(vertices=verts_world, faces=faces)
    except Exception:
        return None


def get_horizontal_projection(mesh, tolerance=0.1):
    """Get 2D projection of mesh at its top level using multiple methods."""
    if mesh is None or mesh.is_empty:
        return None
    
    z_top = mesh.bounds[1, 2]
    
    # Method 1: Use vertices near top
    top_vertices = mesh.vertices[mesh.vertices[:, 2] >= z_top - tolerance]
    if len(top_vertices) >= 3:
        points = [(v[0], v[1]) for v in top_vertices]
        try:
            return sg.MultiPoint(points).convex_hull.buffer(0)
        except Exception:
            pass
    
    # Method 2: Use all vertices projected to 2D
    all_points = [(v[0], v[1]) for v in mesh.vertices]
    if len(all_points) >= 3:
        try:
            return sg.MultiPoint(all_points).convex_hull.buffer(0)
        except Exception:
            pass
    
    return None


def check_slab_guarded(slab_guid, slab_mesh, slab_top_z, slab_proj, 
                       barrier_data, slab_data,
                       min_barrier_height=1.0, max_horiz_gap=0.15, 
                       max_fall=0.5, max_landing_dist=0.1, 
                       min_landing_width=0.2):
    """Check if a slab is properly guarded against falling.
    
    Args:
        slab_guid: GUID of the slab being checked
        slab_mesh: Trimesh object of the slab
        slab_top_z: Top Z coordinate of the slab
        slab_proj: 2D projection of the slab
        barrier_data: Dictionary of barrier geometries
        slab_data: Dictionary of all slab geometries
        min_barrier_height: Minimum required barrier height (m)
        max_horiz_gap: Maximum allowed horizontal gap to barrier (m)
        max_fall: Maximum allowed vertical fall to landing (m)
        max_landing_dist: Maximum horizontal distance to landing (m)
        min_landing_width: Minimum required landing width (m)
    
    Returns:
        bool: True if slab is properly guarded, False otherwise
    """
    if slab_proj is None:
        return False  # Can't verify, assume violation
    
    boundary = slab_proj.boundary
    if boundary is None or boundary.is_empty:
        return False
    
    # Get line segments from boundary
    segments = []
    if boundary.geom_type == 'Polygon':
        coords = list(boundary.exterior.coords)
        segments.append([(coords[i], coords[i+1]) for i in range(len(coords)-1)])
    elif boundary.geom_type == 'MultiLineString':
        for line in boundary.geoms:
            coords = list(line.coords)
            segments.append([(coords[i], coords[i+1]) for i in range(len(coords)-1)])
    elif boundary.geom_type == 'LineString':
        coords = list(boundary.coords)
        segments.append([(coords[i], coords[i+1]) for i in range(len(coords)-1)])
    
    # Flatten segments
    all_segments = [seg for seg_group in segments for seg in seg_group]
    
    if not all_segments:
        return False
    
    # Sample points along each edge segment
    sample_points = []
    for (x1, y1), (x2, y2) in all_segments:
        seg_length = np.sqrt((x2-x1)**2 + (y2-y1)**2)
        if seg_length < 0.01:
            continue
        
        # Calculate outward normal
        dx, dy = x2 - x1, y2 - y1
        nx, ny = -dy, dx
        norm_len = np.sqrt(nx*nx + ny*ny)
        if norm_len > 0:
            nx, ny = nx/norm_len, ny/norm_len
        
        # Sample every 0.15m (at least 2 points per segment)
        num_samples = max(int(seg_length / 0.15), 2)
        for i in range(num_samples + 1):
            t = i / num_samples
            x = x1 + t * (x2 - x1)
            y = y1 + t * (y2 - y1)
            sample_points.append((x, y, nx, ny))
    
    if not sample_points:
        return False
    
    # Check each sample point
    unguarded_points = 0
    
    for x, y, nx, ny in sample_points:
        # Test point just outside the slab
        test_x = x + nx * 0.05
        test_y = y + ny * 0.05
        test_point = sg.Point(test_x, test_y)
        
        # Check for barriers
        has_barrier = False
        
        for bguid, bdata in barrier_data.items():
            if bdata['projection'] is None:
                continue
            
            # Horizontal distance to barrier
            try:
                horiz_dist = test_point.distance(bdata['projection'])
            except Exception:
                continue
            
            if horiz_dist <= max_horiz_gap + 0.05:
                # Check barrier height
                barrier_height = bdata['top_z'] - slab_top_z
                if barrier_height >= min_barrier_height - 0.02:
                    has_barrier = True
                    break
        
        if has_barrier:
            continue
        
        # Check for safe landing (another slab)
        has_landing = False
        for sguid, sdata in slab_data.items():
            if sguid == slab_guid or sdata['projection'] is None:
                continue
            
            # Check horizontal distance
            try:
                horiz_dist = test_point.distance(sdata['projection'])
            except Exception:
                continue
            
            if horiz_dist <= max_landing_dist + 0.05:
                # Check vertical drop
                vertical_drop = slab_top_z - sdata['top_z']
                if 0 < vertical_drop <= max_fall + 0.01:
                    # Check landing width
                    try:
                        landing_width = sdata['projection'].bounds[2] - sdata['projection'].bounds[0]
                        if landing_width >= min_landing_width - 0.01:
                            has_landing = True
                            break
                    except Exception:
                        pass
        
        if not has_landing:
            unguarded_points += 1
    
    # If more than 25% of points are unguarded, it's a violation
    return unguarded_points <= len(sample_points) * 0.25


def check_slabs_guarded_against_falling(path_ifc_model: str) -> List[str]:
    """Check if slabs are guarded against falling.
    
    This rule checks that it is not possible to fall from slabs. The rule checks 
    that horizontal components are surrounded by vertical components, such as walls 
    or railings. If no vertical component exists on the edge of a horizontal component, 
    another horizontal component or stairs needs to continue and the drop to the other 
    horizontal component must not be more than specified.

    Parameters:
    - Include Slab Building Elements: Floor Slabs, Base Slabs, Landings
    - Barrier Components: Wall, Railing, Column, Stair, BuildingElementProxy
    - Min barrier total height: 1 m
    - Max horizontal gap between barriers: 0.1 m
    - Max horizontal gap from platform to barriers: 0.1 m
    - Fall and Landing: Max distance to landing 0.1 m; max fall 0.5 m; min landing width 0.2 m

    Args:
        path_ifc_model: Path to the IFC model file.

    Returns:
        List[str]: List of IFC GUIDs of slabs that violate the rule (are not guarded against falling).

    Example:
        >>> violations = check_slabs_guarded_against_falling('/path/to/model.ifc')
        >>> print(f"Found {len(violations)} unguarded slabs")
    """
    model = ifcopenshell.open(path_ifc_model)
    settings = ifcopenshell.geom.settings()
    
    # Get all slabs (filter for floor-related types)
    slabs = []
    for s in model.by_type('IfcSlab'):
        predef_type = getattr(s, 'PredefinedType', 'NOTDEFINED')
        if predef_type in ['FLOOR', 'BASESLAB', 'ROOF', 'LANDING', 'FLOOR_PRECAST_CONCRETE']:
            slabs.append(s)
    
    if not slabs:
        return []
    
    # Get barrier elements
    barriers = []
    for btype in ['IfcWall', 'IfcRailing', 'IfcColumn', 'IfcStair', 'IfcBuildingElementProxy']:
        barriers.extend(model.by_type(btype))
    
    # Create meshes for barriers
    barrier_data = {}
    skipped_barriers = 0
    for barrier in barriers:
        mesh = create_trimesh_from_element(barrier, settings)
        if mesh is not None:
            proj = get_horizontal_projection(mesh)
            barrier_data[barrier.GlobalId] = {
                'element': barrier,
                'mesh': mesh,
                'top_z': mesh.bounds[1, 2],
                'projection': proj
            }
        else:
            skipped_barriers += 1
    
    # Create meshes for slabs
    slab_data = {}
    skipped_slabs = 0
    for slab in slabs:
        mesh = create_trimesh_from_element(slab, settings)
        if mesh is not None:
            proj = get_horizontal_projection(mesh)
            slab_data[slab.GlobalId] = {
                'element': slab,
                'mesh': mesh,
                'top_z': mesh.bounds[1, 2],
                'projection': proj
            }
        else:
            skipped_slabs += 1
    
    # Check each slab for proper guarding
    violating_slabs = []
    
    for slab in slabs:
        guid = slab.GlobalId
        
        # Skip if no geometry available
        if guid not in slab_data:
            violating_slabs.append(guid)
            continue
        
        sdata = slab_data[guid]
        
        # Check if slab is properly guarded
        is_guarded = check_slab_guarded(
            guid, sdata['mesh'], sdata['top_z'], sdata['projection'],
            barrier_data, slab_data
        )
        
        if not is_guarded:
            violating_slabs.append(guid)
    
    return violating_slabs