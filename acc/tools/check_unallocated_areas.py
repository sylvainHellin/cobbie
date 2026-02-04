import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.geom
import shapely.geometry as sg
import shapely.ops as so
from typing import List, Optional, Tuple


def check_unallocated_areas(path_ifc_model: str) -> List[str]:
    """
    Check for unallocated areas (floor area not assigned to any space) that exceed
    the maximum allowed threshold of 0.50 m².

    This rule checks that space geometry and location are correct by identifying
    floor areas bounded by walls that do not have an IfcSpace assigned.

    Args:
        path_ifc_model: Path to the IFC model file.

    Returns:
        List of IFC GUIDs of walls surrounding unallocated areas that exceed
        0.50 m². Returns empty list if no violations found.

    Example:
        >>> guids = check_unallocated_areas('/path/to/model.ifc')
        >>> print(f'Found {len(guids)} violating walls')
    """
    model = ifcopenshell.open(path_ifc_model)
    settings = ifcopenshell.geom.settings()
    MAX_ALLOWED_AREA = 0.50  # m²

    def get_element_2d_footprint(element) -> Optional[sg.Polygon]:
        """Get the 2D footprint (XY projection) of an element."""
        try:
            shape = ifcopenshell.geom.create_shape(settings, element)
            verts = ifcopenshell.util.shape.get_vertices(shape.geometry)
            coords_2d = [(v[0], v[1]) for v in verts]
            faces = ifcopenshell.util.shape.get_faces(shape.geometry)
            polygons = []
            for face in faces:
                face_coords = [coords_2d[i] for i in face]
                try:
                    poly = sg.Polygon(face_coords)
                    if not poly.is_empty and poly.is_valid:
                        polygons.append(poly)
                except Exception:
                    pass
            if polygons:
                return so.unary_union(polygons)
            return None
        except Exception:
            return None

    def get_storey_elements(storey) -> Tuple[List, List]:
        """Get spaces and walls for a given storey using spatial decomposition."""
        spaces = []
        walls = []

        # Get spaces via IfcRelAggregates decomposition
        for rel in storey.IsDecomposedBy:
            if hasattr(rel, 'RelatedObjects'):
                for obj in rel.RelatedObjects:
                    if obj.is_a() == 'IfcSpace':
                        spaces.append(obj)

        # Get walls with this storey as container
        all_walls = model.by_type('IfcWall')
        for wall in all_walls:
            container = ifcopenshell.util.element.get_container(wall)
            if container == storey:
                walls.append(wall)

        return spaces, walls

    def find_walls_bounding_gap(
        gap_poly: sg.Polygon,
        wall_footprints: dict
    ) -> List[str]:
        """Find walls that bound a given unallocated area gap."""
        bounding_wall_guids = []
        gap_buffered = gap_poly.buffer(0.1)  # Small buffer for touch detection

        for wall_guid, wall_fp in wall_footprints.items():
            if wall_fp.intersects(gap_buffered):
                # Check if this wall actually borders the gap
                intersection = wall_fp.intersection(gap_buffered)
                if not intersection.is_empty:
                    bounding_wall_guids.append(wall_guid)

        return bounding_wall_guids

    violating_wall_guids: List[str] = []

    # Process each storey
    storeys = model.by_type('IfcBuildingStorey')
    for storey in storeys:
        spaces, walls = get_storey_elements(storey)

        if not spaces:
            continue

        # Get space footprints
        space_footprints = []
        for space in spaces:
            fp = get_element_2d_footprint(space)
            if fp:
                space_footprints.append(fp)

        if not space_footprints:
            continue

        # Get wall footprints
        wall_footprints = {}
        for wall in walls:
            fp = get_element_2d_footprint(wall)
            if fp:
                wall_footprints[wall.GlobalId] = fp

        if not wall_footprints:
            continue

        # Create a bounding polygon from walls
        all_walls_union = so.unary_union(list(wall_footprints.values()))
        all_spaces_union = so.unary_union(space_footprints)

        # Find unallocated area: areas within wall bounds but not covered by spaces
        # Create a hull around all walls to define the bounded area
        if all_walls_union.is_empty:
            continue

        # Get the convex hull of walls to define the bounded region
        try:
            wall_hull = all_walls_union.convex_hull
        except Exception:
            continue

        # Unallocated area = wall hull - spaces
        unallocated = wall_hull.difference(all_spaces_union)

        if unallocated.is_empty:
            continue

        # Process each unallocated area component
        if hasattr(unallocated, 'geoms'):
            gap_polys = list(unallocated.geoms)
        else:
            gap_polys = [unallocated]

        for gap in gap_polys:
            if gap.area > MAX_ALLOWED_AREA:
                # Find walls bounding this gap
                bounding_walls = find_walls_bounding_gap(gap, wall_footprints)
                violating_wall_guids.extend(bounding_walls)

    # Remove duplicates while preserving order
    seen = set()
    unique_guids = []
    for guid in violating_wall_guids:
        if guid not in seen:
            seen.add(guid)
            unique_guids.append(guid)

    return unique_guids