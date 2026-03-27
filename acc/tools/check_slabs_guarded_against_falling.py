import ifcopenshell
import ifcopenshell.util.element
import ifcopenshell.util.shape
import ifcopenshell.geom
import numpy as np
import trimesh
import shapely.geometry as sg
import shapely.ops as so
from typing import List, Optional, Tuple

def check_slabs_guarded_against_falling(path_ifc_model: str) -> List[str]:
    """
    Checks if slabs in the IFC model are guarded against falling.

    This rule verifies that horizontal components (slabs) are surrounded by vertical
    components (barriers) or have an acceptable fall to another horizontal component.

    Args:
        path_ifc_model (str): Path to the IFC model file.

    Returns:
        List[str]: List of IFC GUIDs of elements (slabs/footings) that violate the rule.

    Example:
        >>> violations = check_slabs_guarded_against_falling('model.ifc')
        >>> print(f'Found {len(violations)} violations')
    """
    # Configuration parameters
    MIN_BARRIER_HEIGHT = 1.0  # meters
    MAX_GAP_BARRIERS = 0.1  # meters
    MAX_GAP_TO_BARRIER = 0.1  # meters
    MAX_DISTANCE_TO_LANDING = 0.1  # meters
    MAX_FALL_HEIGHT = 0.5  # meters
    MIN_LANDING_WIDTH = 0.2  # meters

    model = ifcopenshell.open(path_ifc_model)
    settings = ifcopenshell.geom.settings()
    settings.set(settings.DISABLE_OPENING_SUBTRACTIONS, False)

    # Helper functions defined inside to maintain single-parameter signature
    def get_element_footprint(element) -> Optional[sg.base.BaseGeometry]:
        try:
            shape = ifcopenshell.geom.create_shape(settings, element)
            verts = shape.geometry.verts
            faces = shape.geometry.faces
            matrix = ifcopenshell.util.shape.get_shape_matrix(shape)
            verts_array = np.array(verts).reshape(-1, 3)
            faces_array = np.array(faces).reshape(-1, 3)
            verts_transformed = np.dot(np.hstack([verts_array, np.ones((verts_array.shape[0], 1))]), matrix.T)[:, :3]
            mesh = trimesh.Trimesh(vertices=verts_transformed, faces=faces_array)
            face_normals = mesh.face_normals
            horizontal_faces = np.where(np.abs(face_normals[:, 2]) > 0.9)[0]
            if len(horizontal_faces) == 0:
                return None
            polygons_2d = []
            for face_idx in horizontal_faces:
                face_verts = verts_transformed[mesh.faces[face_idx]]
                poly = sg.Polygon([(v[0], v[1]) for v in face_verts])
                if not poly.is_empty and poly.area > 0.0001:
                    polygons_2d.append(poly)
            if not polygons_2d:
                return None
            footprint = so.unary_union(polygons_2d)
            if footprint.is_empty or footprint.area < 0.0001:
                return None
            return footprint
        except Exception:
            return None

    def get_element_height(element) -> Tuple[float, float]:
        try:
            shape = ifcopenshell.geom.create_shape(settings, element)
            verts = shape.geometry.verts
            matrix = ifcopenshell.util.shape.get_shape_matrix(shape)
            verts_array = np.array(verts).reshape(-1, 3)
            verts_transformed = np.dot(np.hstack([verts_array, np.ones((verts_array.shape[0], 1))]), matrix.T)[:, :3]
            z_min = verts_transformed[:, 2].min()
            z_max = verts_transformed[:, 2].max()
            return z_min, z_max
        except Exception:
            return 0, 0

    def is_edge_shared_with_slab(edge_line, slab_footprint, other_slabs_footprints, tolerance=0.05) -> bool:
        edge_buffer = edge_line.buffer(tolerance)
        for other_fp in other_slabs_footprints:
            if other_fp.equals(slab_footprint):
                continue
            if edge_buffer.intersects(other_fp):
                intersection = edge_buffer.intersection(other_fp)
                if intersection.area > 0.001:
                    return True
        return False

    def check_edge_guarded(edge_line, slab_z_top, barriers, tolerance=0.01) -> bool:
        if edge_line.length < 0.001:
            return True
        num_samples = max(2, int(edge_line.length / MAX_GAP_BARRIERS) + 1)
        sample_points = [edge_line.interpolate(i / num_samples, normalized=True) for i in range(num_samples + 1)]
        for point in sample_points:
            guarded = False
            for barrier, barrier_footprint, barrier_z_min, barrier_z_max in barriers:
                dist_to_barrier = point.distance(barrier_footprint)
                if dist_to_barrier <= MAX_GAP_TO_BARRIER + tolerance:
                    barrier_height = barrier_z_max - barrier_z_min
                    if barrier_z_max >= slab_z_top - tolerance:
                        if barrier_height >= MIN_BARRIER_HEIGHT - tolerance:
                            guarded = True
                            break
            if not guarded:
                return False
        return True

    def check_acceptable_fall(edge_line, slab_z_top, landings) -> bool:
        if edge_line.length < 0.001:
            return True
        num_samples = max(2, int(edge_line.length / 0.2) + 1)
        sample_points = [edge_line.interpolate(i / num_samples, normalized=True) for i in range(num_samples + 1)]
        for point in sample_points:
            has_acceptable_landing = False
            for landing, landing_footprint, landing_z_min, landing_z_max in landings:
                dist_to_landing = point.distance(landing_footprint)
                if dist_to_landing <= MAX_DISTANCE_TO_LANDING:
                    fall_height = slab_z_top - landing_z_max
                    if 0 < fall_height <= MAX_FALL_HEIGHT:
                        landing_width = landing_footprint.length
                        if landing_width >= MIN_LANDING_WIDTH:
                            has_acceptable_landing = True
                            break
            if not has_acceptable_landing:
                return False
        return True

    # Collect elements
    horizontal_elements = list(model.by_type('IfcSlab'))
    try:
        horizontal_elements.extend(model.by_type('IfcFooting'))
    except AttributeError:
        pass

    barrier_elements = []
    barrier_elements.extend(model.by_type('IfcWall'))
    barrier_elements.extend(model.by_type('IfcRailing'))
    barrier_elements.extend(model.by_type('IfcColumn'))
    barrier_elements.extend(model.by_type('IfcStair'))
    barrier_elements.extend(model.by_type('IfcBuildingElementProxy'))

    landing_elements = list(model.by_type('IfcSlab'))
    try:
        landing_elements.extend(model.by_type('IfcFooting'))
    except AttributeError:
        pass
    landing_elements.extend(model.by_type('IfcSite'))
    landing_elements.extend(model.by_type('IfcStair'))
    try:
        landing_elements.extend(model.by_type('IfcRamp'))
    except AttributeError:
        pass

    # Preprocess geometries
    horizontal_data = []
    for elem in horizontal_elements:
        footprint = get_element_footprint(elem)
        if footprint:
            z_min, z_max = get_element_height(elem)
            horizontal_data.append((elem, footprint, z_min, z_max))

    barriers_data = []
    for barrier in barrier_elements:
        footprint = get_element_footprint(barrier)
        z_min, z_max = get_element_height(barrier)
        if footprint and (z_max - z_min) > 0.01:
            barriers_data.append((barrier, footprint, z_min, z_max))

    landings_data = []
    for landing in landing_elements:
        footprint = get_element_footprint(landing)
        if footprint:
            z_min, z_max = get_element_height(landing)
            landings_data.append((landing, footprint, z_min, z_max))

    all_horizontal_footprints = [fp for _, fp, _, _ in horizontal_data]
    violating_guids = set()

    # Analyze
    for elem, footprint, z_min, z_max in horizontal_data:
        slab_z_top = z_max
        edges = []
        if isinstance(footprint, (sg.Polygon, sg.MultiPolygon)):
            polygons = [footprint] if isinstance(footprint, sg.Polygon) else footprint.geoms
            for poly in polygons:
                exterior_coords = list(poly.exterior.coords)
                for j in range(len(exterior_coords) - 1):
                    edge = sg.LineString([exterior_coords[j], exterior_coords[j + 1]])
                    if edge.length > 0.001:
                        edges.append(edge)

        has_violation = False
        for edge in edges:
            if is_edge_shared_with_slab(edge, footprint, all_horizontal_footprints):
                continue
            if not check_edge_guarded(edge, slab_z_top, barriers_data):
                if not check_acceptable_fall(edge, slab_z_top, landings_data):
                    has_violation = True
                    break
        if has_violation:
            violating_guids.add(elem.GlobalId)

    return list(violating_guids)
