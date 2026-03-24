import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.geom
import trimesh
import shapely.geometry
import shapely.ops
import numpy as np
from typing import List, Dict, Optional, Tuple


def check_unallocated_areas(path_ifc_model: str) -> List[str]:
    """
    Detect unallocated areas in an IFC model and return GUIDs of surrounding walls.

    This rule checks that space geometry and location are correct by identifying
    floor areas not assigned to any space that exceed the maximum allowed threshold.
    For each unallocated area found, the surrounding walls are identified and their
    GUIDs are returned.

    Parameters:
        Maximum allowed Unallocated space: 0.50 m²
        Return Surrounding Walls: Yes

    Args:
        path_ifc_model: Path to the IFC model file

    Returns:
        List of IFC GUIDs of walls surrounding unallocated areas that exceed 0.50 m².
        Returns empty list if no violations found or if model cannot be processed.

    Example:
        >>> guids = check_unallocated_areas('/path/to/model.ifc')
        >>> print(f"Found {len(guids)} violations")
    """
    if not path_ifc_model:
        return []

    try:
        model = ifcopenshell.open(path_ifc_model)
    except Exception as e:
        print(f"Error opening IFC file: {e}")
        return []

    # Configure geometry settings for 2D Plan representations
    settings = ifcopenshell.geom.settings()
    settings.set('disable-opening-subtractions', True)
    settings.set('context-types', ['Plan'])

    def get_element_footprint(element, geom_settings=None) -> Optional[shapely.geometry.Polygon]:
        """Extract 2D footprint from IFC element using horizontal section."""
        if geom_settings is None:
            geom_settings = settings

        try:
            shape = ifcopenshell.geom.create_shape(geom_settings, element)
            verts = shape.geometry.verts
            faces = shape.geometry.faces

            verts_array = np.array(verts).reshape(-1, 3)
            faces_array = np.array(faces).reshape(-1, 3)

            if len(faces_array) == 0:
                return None

            mesh = trimesh.Trimesh(vertices=verts_array, faces=faces_array)

            bounds = mesh.bounds
            z_min, z_max = bounds[0, 2], bounds[1, 2]
            section_z = (z_min + z_max) / 2

            section = mesh.section(plane_origin=[0, 0, section_z], plane_normal=[0, 0, 1])

            if section:
                path2d = section.to_planar()[0]
                if hasattr(path2d, 'polygons_full') and len(path2d.polygons_full) > 0:
                    return shapely.ops.unary_union(path2d.polygons_full)
                elif hasattr(path2d, 'polygons') and len(path2d.polygons) > 0:
                    return shapely.ops.unary_union(path2d.polygons)

            return None
        except Exception:
            return None

    def get_wall_centerline(wall, geom_settings=None) -> Optional[shapely.geometry.LineString]:
        """Extract 2D centerline from wall footprint."""
        footprint = get_element_footprint(wall, geom_settings)
        if footprint and not footprint.is_empty:
            try:
                # Simplify to centerline using medial axis or approximation
                if hasattr(footprint, 'interior') and len(list(footprint.interior.geoms)) > 0:
                    # For walls with holes (like with openings), get main exterior
                    exterior = footprint.exterior
                    if len(exterior.coords) >= 2:
                        return shapely.geometry.LineString(list(exterior.coords)[:2])
                else:
                    # For simple walls, use the longest edge as centerline approximation
                    coords = list(footprint.exterior.coords)
                    if len(coords) >= 2:
                        max_dist = 0
                        best_line = None
                        for i in range(len(coords) - 1):
                            p1 = shapely.geometry.Point(coords[i])
                            p2 = shapely.geometry.Point(coords[i + 1])
                            dist = p1.distance(p2)
                            if dist > max_dist:
                                max_dist = dist
                                best_line = shapely.geometry.LineString([coords[i], coords[i + 1]])
                        return best_line
            except Exception:
                pass
        return None

    def get_surrounding_walls(walls: List, polygon: shapely.geometry.Polygon, geom_settings=None) -> List[str]:
        """Find walls that surround the given polygon."""
        surrounding = []
        for wall in walls:
            footprint = get_element_footprint(wall, geom_settings)
            if footprint and not footprint.is_empty:
                if footprint.intersects(polygon) or footprint.touches(polygon):
                    # Check proximity
                    if footprint.distance(polygon) < 0.3:
                        surrounding.append(wall.GlobalId)
        return surrounding

    def is_structural_floor_slab(slab) -> bool:
        """Check if slab is a structural floor (not finish floor)."""
        name = getattr(slab, 'Name', '')
        predefined_type = getattr(slab, 'PredefinedType', None)
        # Exclude finish floors
        if 'Finish Floor' in name:
            return False
        if predefined_type == 'FLOOR':
            return True
        return True

    # Main processing
    all_violation_guids = []
    skipped_elements = 0

    for storey in model.by_type('IfcBuildingStorey'):
        try:
            elements = ifcopenshell.util.element.get_decomposition(storey)

            walls_in_storey = [e for e in elements if e.is_a('IfcWall')]
            spaces_in_storey = [e for e in elements if e.is_a('IfcSpace')]
            slabs_in_storey = [e for e in elements if e.is_a('IfcSlab') and is_structural_floor_slab(e)]

            if not walls_in_storey or not spaces_in_storey:
                continue

            # Create wall buffer from wall centerlines
            wall_centerlines = []
            for wall in walls_in_storey:
                centerline = get_wall_centerline(wall, settings)
                if centerline:
                    wall_centerlines.append(centerline)
                else:
                    skipped_elements += 1

            if not wall_centerlines:
                continue

            # Create minimal wall buffer (wall thickness approximation)
            wall_buffer = shapely.ops.unary_union(wall_centerlines).buffer(0.2, cap_style=2)

            # Get space footprints
            space_polygons = []
            for space in spaces_in_storey:
                footprint = get_element_footprint(space, settings)
                if footprint:
                    space_polygons.append(footprint)

            # Get structural floor slab footprints
            slab_polygons = []
            for slab in slabs_in_storey:
                footprint = get_element_footprint(slab, settings)
                if footprint:
                    slab_polygons.append(footprint)

            # Calculate unallocated area
            total_spaces = shapely.ops.unary_union(space_polygons) if space_polygons else shapely.geometry.Polygon()
            total_slabs = shapely.ops.unary_union(slab_polygons) if slab_polygons else shapely.geometry.Polygon()

            unallocated = wall_buffer.difference(total_spaces).difference(total_slabs)

            # Check threshold and find surrounding walls
            if unallocated.geom_type == 'MultiPolygon':
                for poly in unallocated.geoms:
                    if poly.area > 0.50:
                        walls = get_surrounding_walls(walls_in_storey, poly, settings)
                        all_violation_guids.extend(walls)
            elif unallocated.area > 0.50:
                walls = get_surrounding_walls(walls_in_storey, unallocated, settings)
                all_violation_guids.extend(walls)

        except Exception as e:
            skipped_elements += 1
            continue

    if skipped_elements > 0:
        print(f"Warning: Skipped {skipped_elements} elements during processing")

    return list(set(all_violation_guids))
