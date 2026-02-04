import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.shape
import numpy as np
import shapely.geometry as geom
from typing import List, Dict, Tuple, Optional, Set
from scipy.spatial import ConvexHull
import multiprocessing

# Parameters from the rule
MIN_BARRIER_HEIGHT = 1.0  # meters
MAX_GAP_PLATFORM = 0.1  # meters
MAX_FALL = 0.5  # meters
MAX_DISTANCE_LANDING = 0.1  # meters
MIN_LANDING_WIDTH = 0.2  # meters
EDGE_SAMPLE_INTERVAL = 0.25  # Sample every 25cm

def check_slabs_guarded_against_falling(path_ifc_model: str) -> List[str]:
    """
    Check if slabs are guarded against falling.
    
    This rule checks that it is not possible to fall from slabs. The rule checks that
    horizontal components are surrounded by vertical components, such as walls or railings.
    If no vertical component exists on the edge of a horizontal component, another horizontal
    component or stairs needs to continue and the drop to the other horizontal component
    must not be more than specified.
    
    Args:
        path_ifc_model: Path to the IFC model file.
        
    Returns:
        List of IFC GUIDs of all slab elements that violate this rule.
        
    Example:
        >>> violations = check_slabs_guarded_against_falling('/path/to/model.ifc')
        >>> print(f"Found {len(violations)} violations")
    """
    model = ifcopenshell.open(path_ifc_model)
    
    def get_element_geometry_with_height(element):
        """Extract world coordinate geometry and height info for an element."""
        try:
            settings = ifcopenshell.geom.settings()
            shape = ifcopenshell.geom.create_shape(settings, element)
            verts = ifcopenshell.util.shape.get_vertices(shape.geometry)
            matrix = ifcopenshell.util.shape.get_shape_matrix(shape)
            
            verts_homogeneous = np.hstack([verts, np.ones((len(verts), 1))])
            verts_world = (matrix @ verts_homogeneous.T).T[:, :3]
            
            z_min = verts_world[:, 2].min()
            z_max = verts_world[:, 2].max()
            height = z_max - z_min
            
            return verts_world, z_min, z_max, height
        except Exception:
            return None, None, None, None
    
    def get_top_face_polygon(verts_world: np.ndarray) -> Optional[geom.Polygon]:
        """Extract the top face of a slab as a 2D polygon."""
        if verts_world is None or len(verts_world) < 3:
            return None
        
        z_max = verts_world[:, 2].max()
        z_tolerance = 0.02
        
        top_mask = np.abs(verts_world[:, 2] - z_max) < z_tolerance
        top_verts = verts_world[top_mask][:, :2]
        
        if len(top_verts) < 3:
            return None
        
        try:
            hull = ConvexHull(top_verts)
            boundary_verts = top_verts[hull.vertices]
            return geom.Polygon(boundary_verts)
        except Exception:
            try:
                return geom.MultiPoint(top_verts).convex_hull
            except Exception:
                return None
    
    def get_edge_points_by_interval(polygon: geom.Polygon, interval: float = EDGE_SAMPLE_INTERVAL) -> List[Tuple[float, float]]:
        """Sample points along polygon edges at specified intervals."""
        if polygon.is_empty:
            return []
        
        points = []
        coords = list(polygon.exterior.coords)
        
        for i in range(len(coords) - 1):
            p1 = np.array(coords[i])
            p2 = np.array(coords[i + 1])
            
            dist = np.linalg.norm(p2 - p1)
            num_samples = max(2, int(dist / interval) + 1)
            
            for j in range(num_samples):
                t = j / (num_samples - 1)
                point = p1 + t * (p2 - p1)
                points.append((point[0], point[1]))
        
        # Remove duplicates
        unique_points = []
        for p in points:
            is_duplicate = False
            for up in unique_points:
                if np.linalg.norm(np.array(p) - np.array(up)) < 0.001:
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique_points.append(p)
        
        return unique_points
    
    def build_geometry_tree():
        """Build a geometry tree for spatial queries."""
        tree = ifcopenshell.geom.tree()
        settings = ifcopenshell.geom.settings()
        iterator = ifcopenshell.geom.iterator(settings, model, multiprocessing.cpu_count())
        
        if iterator.initialize():
            while True:
                tree.add_element(iterator.get())
                if not iterator.next():
                    break
        
        return tree
    
    def cache_element_geometry(element_types: List[str]) -> Dict[str, Dict]:
        """Cache geometry info including 2D footprint for elements."""
        cache = {}
        skipped = 0
        
        for etype in element_types:
            for elem in model.by_type(etype):
                try:
                    geom_data, z_min, z_max, height = get_element_geometry_with_height(elem)
                    if geom_data is not None:
                        verts_2d = geom_data[:, :2]
                        cache[elem.GlobalId] = {
                            'z_min': z_min,
                            'z_max': z_max,
                            'height': height,
                            'type': elem.is_a(),
                            'verts_2d': verts_2d
                        }
                except Exception:
                    skipped += 1
                    continue
        
        if skipped > 0:
            print(f"Warning: Skipped {skipped} elements due to geometry processing errors")
        
        return cache
    
    def check_point_protection(point: Tuple[float, float], slab_z_min: float,
                               tree, geom_cache: Dict,
                               barrier_types: Set, landing_types: Set) -> Tuple[bool, str]:
        """Check if a point is protected using geometry tree and cached geometry."""
        px, py = point
        search_radius = 0.5
        
        try:
            nearby_elements = tree.select((px, py, slab_z_min), extend=search_radius)
        except Exception:
            try:
                nearby_elements = tree.select((px, py, slab_z_min))
            except Exception:
                return False, "query_error"
        
        found_adequate_barrier = False
        found_low_barrier = False
        
        for elem in nearby_elements:
            if elem.GlobalId not in geom_cache:
                continue
            
            info = geom_cache[elem.GlobalId]
            
            if info['type'] in barrier_types:
                if info['z_max'] < slab_z_min - 0.3:
                    continue
                if info['z_min'] > slab_z_min + 0.3:
                    continue
                
                verts_2d = info['verts_2d']
                distances = np.sqrt((verts_2d[:, 0] - px)**2 + (verts_2d[:, 1] - py)**2)
                min_dist = distances.min()
                
                if min_dist <= MAX_GAP_PLATFORM:
                    if info['height'] >= MIN_BARRIER_HEIGHT:
                        return True, "adequate_barrier"
                    elif info['height'] > 0.2:
                        found_low_barrier = True
            
            elif info['type'] in landing_types:
                if info['type'] == 'IfcSlab':
                    if abs(info['z_min'] - slab_z_min) < 0.1:
                        continue
                
                fall_height = slab_z_min - info['z_max']
                
                if 0 < fall_height <= MAX_FALL:
                    verts_2d = info['verts_2d']
                    distances = np.sqrt((verts_2d[:, 0] - px)**2 + (verts_2d[:, 1] - py)**2)
                    min_dist = distances.min()
                    
                    if min_dist <= MAX_DISTANCE_LANDING:
                        try:
                            landing_poly = geom.MultiPoint(verts_2d).convex_hull
                            min_dim = min(landing_poly.bounds[2] - landing_poly.bounds[0],
                                          landing_poly.bounds[3] - landing_poly.bounds[1])
                            if min_dim >= MIN_LANDING_WIDTH:
                                return True, "acceptable_fall"
                        except Exception:
                            pass
        
        if found_low_barrier:
            return False, "low_barrier"
        
        return False, "no_protection"
    
    def check_slab_falling_protection(slab, tree, geom_cache: Dict,
                                       barrier_types: Set, landing_types: Set) -> Tuple[bool, str]:
        """Check if a slab is properly guarded against falling."""
        slab_geom, slab_z_min, slab_z_max, _ = get_element_geometry_with_height(slab)
        if slab_geom is None:
            return True, "no_geometry"
        
        slab_poly = get_top_face_polygon(slab_geom)
        if slab_poly is None:
            return True, "no_polygon"
        
        edge_points = get_edge_points_by_interval(slab_poly, interval=EDGE_SAMPLE_INTERVAL)
        if not edge_points:
            return True, "no_edge_points"
        
        unprotected_count = 0
        low_barrier_count = 0
        
        for point in edge_points:
            is_protected, reason = check_point_protection(
                point, slab_z_min, tree, geom_cache, barrier_types, landing_types
            )
            
            if not is_protected:
                if reason == "low_barrier":
                    low_barrier_count += 1
                else:
                    unprotected_count += 1
        
        if unprotected_count > 0:
            return False, "missing_barriers"
        
        if low_barrier_count > 0:
            return False, "low_barriers"
        
        return True, "protected"
    
    # Main execution
    if not model:
        return []
    
    print("Building geometry tree...")
    tree = build_geometry_tree()
    
    print("Caching element geometry...")
    barrier_types = {'IfcWall', 'IfcRailing', 'IfcColumn', 'IfcStair', 'IfcBuildingElementProxy'}
    landing_types = {'IfcSlab', 'IfcSite', 'IfcStair', 'IfcRamp'}
    all_types = list(barrier_types | landing_types)
    
    geom_cache = cache_element_geometry(all_types)
    print(f"Cached {len(geom_cache)} elements")
    
    print("Checking slabs...")
    slabs = model.by_type('IfcSlab')
    floor_slabs = [s for s in slabs if getattr(s, 'PredefinedType', None) in ('FLOOR', 'BASESLAB')]
    
    if not floor_slabs:
        print("No floor slabs found in model")
        return []
    
    violations = []
    
    for i, slab in enumerate(floor_slabs):
        is_protected, reason = check_slab_falling_protection(
            slab, tree, geom_cache, barrier_types, landing_types
        )
        
        if not is_protected:
            violations.append(slab.GlobalId)
        
        if (i + 1) % 10 == 0:
            print(f"  Processed {i + 1}/{len(floor_slabs)} slabs, {len(violations)} violations found")
    
    print(f"Total violations: {len(violations)}")
    return violations