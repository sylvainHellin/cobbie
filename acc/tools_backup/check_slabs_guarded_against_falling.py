import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.shape
import numpy as np
import shapely.geometry as sg
from typing import List, Dict, Optional

# Rule Parameters
MIN_BARRIER_HEIGHT = 1.0       # meters
MAX_GAP_BARRIER = 0.1        # meters (horizontal/vertical)
MAX_GAP_LANDING = 0.1        # meters (distance to landing)
MAX_FALL_HEIGHT = 0.5        # meters
SAMPLING_INTERVAL = 0.2      # meters (increased for efficiency)

def _get_element_geometry(model: ifcopenshell.file, element, settings) -> Optional[Dict]:
    """
    Extracts 2D footprint and Z-bounds from an IFC element.
    """
    try:
        shape = ifcopenshell.geom.create_shape(settings, element)
        verts = ifcopenshell.util.shape.get_vertices(shape.geometry)
        
        if len(verts) == 0:
            return None
            
        # Transform vertices to world coordinates
        matrix = ifcopenshell.util.shape.get_shape_matrix(shape)
        ones = np.ones((verts.shape[0], 1))
        verts_h = np.hstack([verts, ones])
        verts_world = (matrix @ verts_h.T).T[:, :3]
        
        min_z = np.min(verts_world[:, 2])
        max_z = np.max(verts_world[:, 2])
        
        # Create 2D footprint using convex hull for robustness
        points_2d = [sg.Point(v[0], v[1]) for v in verts_world]
        if not points_2d:
            return None
            
        multi_point = sg.MultiPoint(points_2d)
        poly_2d = multi_point.convex_hull
        
        if poly_2d.is_empty or poly_2d.area < 1e-6:
            return None
            
        return {
            'guid': element.GlobalId,
            'type': element.is_a(),
            'max_z': max_z,
            'min_z': min_z,
            'poly': poly_2d,
            'bounds': poly_2d.bounds
        }
    except (RuntimeError, AttributeError, ValueError):
        return None

def check_slabs_guarded_against_falling(path_ifc_model: str) -> List[str]:
    """
    Checks if slabs in the IFC model are guarded against falling.
    
    The rule checks that horizontal components (slabs) are surrounded by vertical
    components (barriers) or have an acceptable drop to a landing surface.

    Args:
        path_ifc_model: Path to the IFC file.

    Returns:
        List of IFC GUIDs of slabs that violate the rule (unguarded edges).
        Returns an empty list if no violations are found or if model is empty.
        
    Rules Applied:
    - Slab Types: Floor, BaseSlab, Balcony.
    - Barrier Types: Wall, Railing, BuildingElementProxy, Column, Stair.
    - Landing Types: Slab, Stair, Ramp, Site.
    - Min barrier height: 1.0 m (relative to slab).
    - Max gap to barrier/landing: 0.1 m.
    - Max fall height: 0.5 m.
    """
    model = ifcopenshell.open(path_ifc_model)
    settings = ifcopenshell.geom.settings()
    
    # 1. Identify Elements by IFC Type and PredefinedType
    # Target Slabs
    all_slabs = model.by_type('IfcSlab')
    target_slabs = []
    
    # Slab types to check (from requirements: Floor Slabs, Balconies)
    valid_slab_types = {'FLOOR', 'BASESLAB', 'BALCONY'}
    
    for s in all_slabs:
        ptype = getattr(s, 'PredefinedType', 'NOTDEFINED')
        # Check if PredefinedType is valid
        if ptype in valid_slab_types:
            target_slabs.append(s)
            
    if not target_slabs:
        return []
    
    # Barrier Components: Wall, Railing, Object (Proxy), Column, Stair
    barriers = model.by_type('IfcWall') + model.by_type('IfcRailing') + \
              model.by_type('IfcBuildingElementProxy') + model.by_type('IfcColumn') + \
              model.by_type('IfcStair')
              
    # Fall and Landing: Slab, Stair, Ramp, Site
    landings = model.by_type('IfcSlab') + model.by_type('IfcStair') + \
               model.by_type('IfcRamp')
    
    # Check Sites for geometry
    sites = model.by_type('IfcSite')
    for site in sites:
        if hasattr(site, 'Representation') and site.Representation is not None:
            landings.append(site)
    
    # 2. Extract Geometry
    unique_elements = list(set(target_slabs + barriers + landings))
    
    geom_map = {}
    skipped_count = 0
    
    for elem in unique_elements:
        geom = _get_element_geometry(model, elem, settings)
        if geom:
            geom_map[geom['guid']] = geom
        else:
            skipped_count += 1
            
    if skipped_count > 0:
        print(f"Warning: Skipped {skipped_count} elements due to geometry errors.")
    
    # 3. Categorize Geometries
    slab_geoms = [g for g in geom_map.values() if g['guid'] in {s.GlobalId for s in target_slabs}]
    barrier_geoms = [g for g in geom_map.values() if g['guid'] in {b.GlobalId for b in barriers}]
    landing_geoms = [g for g in geom_map.values() if g['guid'] in {l.GlobalId for l in landings}]
    
    violating_guids = []
    
    # 4. Analyze Each Slab
    for slab in slab_geoms:
        slab_guid = slab['guid']
        slab_poly = slab['poly']
        slab_z = slab['max_z']
        
        # Prepare polygons to check (exterior + holes)
        polygons = []
        if slab_poly.geom_type == 'Polygon':
            polygons.append(slab_poly)
        elif slab_poly.geom_type == 'MultiPolygon':
            polygons.extend(list(slab_poly.geoms))
            
        is_safe = True
        
        for poly in polygons:
            if not is_safe:
                break
            
            # Check all rings (exterior and interior holes)
            rings = [poly.exterior] + list(poly.interiors)
            
            for ring in rings:
                if not is_safe:
                    break
                
                length = ring.length
                if length == 0:
                    continue
                
                # Sample points along the edge
                num_samples = max(2, int(length / SAMPLING_INTERVAL))
                points_on_edge = [ring.interpolate(i / num_samples, normalized=True) for i in range(num_samples)]
                
                for pt in points_on_edge:
                    # A. Check for Valid Barrier
                    has_barrier = False
                    
                    for bar in barrier_geoms:
                        if bar['guid'] == slab_guid:
                            continue
                        
                        # Height Check: Barrier top must be >= Slab top + Min Height
                        required_barrier_height = slab_z + MIN_BARRIER_HEIGHT
                        if bar['max_z'] < required_barrier_height:
                            continue
                            
                        # Horizontal Distance Check
                        dist = bar['poly'].distance(pt)
                        if dist <= MAX_GAP_BARRIER:
                            has_barrier = True
                            break
                    
                    if has_barrier:
                        continue
                        
                    # B. Check for Safe Landing
                    has_landing = False
                    
                    for land in landing_geoms:
                        if land['guid'] == slab_guid:
                            continue
                        
                        # Horizontal Distance Check
                        dist = land['poly'].distance(pt)
                        if dist > MAX_GAP_LANDING:
                            continue
                            
                        # Vertical Drop Check
                        fall_height = slab_z - land['max_z']
                        
                        # Safe if: step up/flat (fall_height <= 0) OR small drop (fall_height <= MAX_FALL_HEIGHT)
                        if fall_height <= 0 or fall_height <= MAX_FALL_HEIGHT:
                            has_landing = True
                            break
                    
                    if not has_barrier and not has_landing:
                        is_safe = False
                        break
        
        if not is_safe:
            violating_guids.append(slab_guid)
    
    return violating_guids