import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.geom
import trimesh
import numpy as np
from shapely.geometry import Polygon, MultiPolygon
from shapely.ops import unary_union
from typing import List, Dict, Any, Optional, Tuple
import warnings
warnings.filterwarnings('ignore')


def check_unallocated_areas(path_ifc_model: str) -> List[str]:
    """
    Check for unallocated areas in an IFC model.

    Identifies floor areas not assigned to any space that exceed the maximum allowed
    area (0.50 m²) and returns the GUIDs of surrounding walls.

    This function:
    1. Extracts 2D floor polygons from all IfcSpace elements
    2. Extracts floor polygons from all IfcWall elements
    3. Groups elements by building storey (using spatial container for walls,
       Z-level matching for spaces)
    4. Creates a floor slab boundary from wall polygons
    5. Finds unallocated areas (difference between floor slab and spaces)
    6. Returns GUIDs of walls surrounding unallocated areas > 0.50 m²

    Args:
        path_ifc_model: Path to the IFC model file.

    Returns:
        List of IFC GUIDs of walls surrounding unallocated areas that exceed
        the maximum allowed area. Returns empty list if no violations found.

    Example:
        >>> guids = check_unallocated_areas('/path/to/model.ifc')
        >>> print(f"Found {len(guids)} violations")
    """
    model = ifcopenshell.open(path_ifc_model)
    max_allowed_area = 0.50
    
    # Get all spaces and walls
    spaces = list(model.by_type('IfcSpace'))
    walls = list(model.by_type('IfcWallStandardCase'))
    
    if not spaces:
        return []
    
    def get_floor_polygon(element) -> Optional[Polygon]:
        """Extract 2D floor polygon from an IFC element."""
        settings = ifcopenshell.geom.settings()
        try:
            shape = ifcopenshell.geom.create_shape(settings, element)
            verts = shape.geometry.verts
            faces = shape.geometry.faces
            
            verts_array = np.array(verts).reshape(-1, 3)
            faces_array = np.array(faces).reshape(-1, 3)
            
            mesh = trimesh.Trimesh(vertices=verts_array, faces=faces_array)
            z_min, z_max = mesh.bounds[:, 2]
            
            # Try multiple section heights to find floor section
            for offset in [0.01, 0.05, 0.1, (z_max - z_min) / 3]:
                section = mesh.section(
                    plane_origin=[0, 0, z_min + offset],
                    plane_normal=[0, 0, 1]
                )
                if section is not None:
                    path2d, _ = section.to_planar()
                    polygons = path2d.polygons_full
                    if polygons:
                        return polygons[0]
            return None
        except Exception:
            return None
    
    def get_element_z_range(element) -> Tuple[float, float]:
        """Get Z range of an element from its geometry."""
        settings = ifcopenshell.geom.settings()
        try:
            shape = ifcopenshell.geom.create_shape(settings, element)
            verts = shape.geometry.verts
            verts_array = np.array(verts).reshape(-1, 3)
            z_coords = verts_array[:, 2]
            return float(np.min(z_coords)), float(np.max(z_coords))
        except Exception:
            return 0.0, 0.0
    
    # Group walls by storey using get_container
    storey_walls: Dict[Any, List] = {}
    storey_z_ranges: Dict[Any, Tuple[float, float]] = {}
    
    for wall in walls:
        try:
            container = ifcopenshell.util.element.get_container(wall)
            if container and container.is_a('IfcBuildingStorey'):
                storey = container
                if storey not in storey_walls:
                    storey_walls[storey] = []
                    storey_z_ranges[storey] = (float('inf'), float('-inf'))
                storey_walls[storey].append(wall)
                
                z_min, z_max = get_element_z_range(wall)
                storey_z_ranges[storey] = (
                    min(storey_z_ranges[storey][0], z_min),
                    max(storey_z_ranges[storey][1], z_max)
                )
        except (AttributeError, Exception):
            pass
    
    # Assign spaces to storeys based on Z overlap
    storey_spaces: Dict[Any, List] = {}
    for space in spaces:
        z_min, z_max = get_element_z_range(space)
        z_mid = (z_min + z_max) / 2
        
        matched_storey = None
        for storey, (storey_zmin, storey_zmax) in storey_z_ranges.items():
            if z_mid >= storey_zmin and z_mid <= storey_zmax:
                matched_storey = storey
                break
        
        if matched_storey is not None:
            if matched_storey not in storey_spaces:
                storey_spaces[matched_storey] = []
            storey_spaces[matched_storey].append(space)
    
    violating_guids: List[str] = []
    
    # Process each storey
    for storey in storey_spaces:
        space_list = storey_spaces[storey]
        wall_list = storey_walls.get(storey, [])
        
        # Extract space polygons
        space_polys: List[Polygon] = []
        for space in space_list:
            poly = get_floor_polygon(space)
            if poly and not poly.is_empty:
                space_polys.append(poly)
        
        if not space_polys:
            continue
        
        # Extract wall polygons and create GUID map
        wall_polys: List[Tuple[Polygon, str]] = []
        for wall in wall_list:
            poly = get_floor_polygon(wall)
            if poly and not poly.is_empty:
                wall_polys.append((poly, wall.GlobalId))
        
        # Union of all space polygons
        try:
            spaces_union = unary_union(space_polys)
        except Exception:
            continue
        
        # Create floor slab from union of wall polygons
        if not wall_polys:
            continue
        
        all_wall_polys_union = unary_union([wp[0] for wp in wall_polys])
        floor_slab = all_wall_polys_union.buffer(0.02)
        floor_slab = floor_slab.buffer(-0.02)
        
        # Find unallocated areas
        unallocated = floor_slab.difference(spaces_union)
        
        if unallocated.is_empty:
            continue
        
        # Handle both Polygon and MultiPolygon
        if isinstance(unallocated, MultiPolygon):
            gap_list = list(unallocated.geoms)
        else:
            gap_list = [unallocated]
        
        # Check each gap
        for gap in gap_list:
            if gap.area > max_allowed_area:
                # Find walls that surround this gap using proximity
                surrounding_walls: List[str] = []
                
                for wall_poly, wall_guid in wall_polys:
                    dist = gap.distance(wall_poly)
                    
                    # Wall is considered surrounding if:
                    # 1. It's very close to the gap (likely boundary)
                    # 2. Or it intersects the gap
                    if dist < 0.3 or gap.intersects(wall_poly):
                        surrounding_walls.append(wall_guid)
                
                # If too many walls found, limit to closest ones
                if len(surrounding_walls) > 6:
                    wall_distances = [
                        (gap.distance(wp[0]), guid)
                        for wp, guid in wall_polys
                    ]
                    wall_distances.sort(key=lambda x: x[0])
                    surrounding_walls = [wd[1] for wd in wall_distances[:6]]
                
                violating_guids.extend(surrounding_walls)
    
    return violating_guids