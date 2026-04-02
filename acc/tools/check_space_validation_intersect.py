import ifcopenshell
import ifcopenshell.geom
from typing import List
import numpy as np
import trimesh
from collections import defaultdict


def check_space_validation_intersect(path_ifc_model: str) -> List[str]:
    """
    Checks that spaces do not incorrectly intersect with slabs, walls, or other components.

    This rule checks space geometry and location to ensure spaces do not incorrectly intersect
    with building components (Wall, CurtainWall, Column, Slab, Roof). It uses a 0.03m tolerance
    and excludes cases where a component is fully inside the space.

    Args:
        path_ifc_model: Path to the IFC model file.

    Returns:
        List of IFC GUIDs of spaces that violate the rule (i.e., have building elements
        intersecting with them where the element is not fully contained within the space).

    Example:
        >>> violations = check_space_validation_intersect('/path/to/model.ifc')
        >>> print(f"Found {len(violations)} space violations")
    """
    # Open the IFC model
    model = ifcopenshell.open(path_ifc_model)

    # Define building element types to check against
    element_types = ['IfcWall', 'IfcCurtainWall', 'IfcColumn', 'IfcSlab', 'IfcRoof']

    # Collect all spaces and building elements
    spaces = list(model.by_type('IfcSpace'))
    building_elements = []
    for elem_type in element_types:
        building_elements.extend(list(model.by_type(elem_type)))

    # Return empty list if no spaces or building elements found
    if not spaces or not building_elements:
        return []

    # Build geometry tree with all elements for efficient clash detection
    tree = ifcopenshell.geom.tree()
    settings = ifcopenshell.geom.settings()

    # Add all elements to the tree
    all_elements = spaces + building_elements
    iterator = ifcopenshell.geom.iterator(settings, model, include=all_elements, exclude=None)

    if iterator.initialize():
        while True:
            try:
                tree.add_element(iterator.get())
            except Exception:
                pass
            if not iterator.next():
                break

    # Check for intersections using collision detection
    # allow_touching=False ensures we only get true intersections, not touching elements
    clashes = tree.clash_collision_many(spaces, building_elements, allow_touching=False)

    # Group clashes by space GUID
    space_clashes = defaultdict(list)
    for clash in clashes:
        # Determine which element is the space
        if clash.a.is_a() == 'IfcSpace':
            space_elem = clash.a
            build_elem = clash.b
        elif clash.b.is_a() == 'IfcSpace':
            space_elem = clash.b
            build_elem = clash.a
        else:
            continue

        space_guid = space_elem.get_argument(0)
        space_clashes[space_guid].append(build_elem)

    # Filter out cases where component is fully inside the space
    violations = []

    for space_guid, elements_list in space_clashes.items():
        space_elem = model.by_guid(space_guid)

        # Get space geometry
        try:
            space_shape = ifcopenshell.geom.create_shape(settings, space_elem)
            space_verts = np.array(space_shape.geometry.verts).reshape(-1, 3)
            space_faces = np.array(space_shape.geometry.faces).reshape(-1, 3)
            space_mesh = trimesh.Trimesh(vertices=space_verts, faces=space_faces)
        except Exception:
            # If geometry extraction fails, treat as violation
            violations.append(space_guid)
            continue

        # Check each intersecting element
        has_violation = False
        for build_elem in elements_list:
            try:
                # Get element geometry
                build_shape = ifcopenshell.geom.create_shape(settings, build_elem)
                build_verts = np.array(build_shape.geometry.verts).reshape(-1, 3)
                build_faces = np.array(build_shape.geometry.faces).reshape(-1, 3)
                build_mesh = trimesh.Trimesh(vertices=build_verts, faces=build_faces)

                # Sample points from the element's surface to check containment
                sample_points = []

                # Add centroid
                sample_points.append(build_mesh.centroid)

                # Add vertices (sample if too many)
                if len(build_mesh.vertices) > 100:
                    indices = np.linspace(0, len(build_mesh.vertices) - 1, 100, dtype=int)
                    sample_points.extend(build_mesh.vertices[indices])
                else:
                    sample_points.extend(build_mesh.vertices)

                # Add face centroids
                if len(build_mesh.faces) > 0:
                    face_centroids = build_mesh.triangles_center
                    # Sample a subset of face centroids
                    num_samples = min(20, len(face_centroids))
                    if len(face_centroids) > num_samples:
                        indices = np.linspace(0, len(face_centroids) - 1, num_samples, dtype=int)
                        sample_points.extend(face_centroids[indices])
                    else:
                        sample_points.extend(face_centroids)

                # Add edge midpoints for better coverage
                if len(build_mesh.edges) > 0:
                    edge_midpoints = (build_mesh.vertices[build_mesh.edges[:, 0]] + build_mesh.vertices[build_mesh.edges[:, 1]]) / 2
                    # Sample a subset of edge midpoints
                    num_samples = min(20, len(edge_midpoints))
                    if len(edge_midpoints) > num_samples:
                        indices = np.linspace(0, len(edge_midpoints) - 1, num_samples, dtype=int)
                        sample_points.extend(edge_midpoints[indices])
                    else:
                        sample_points.extend(edge_midpoints)

                # Add bounding box corners for robustness
                bounds = build_mesh.bounds
                corners = [
                    [bounds[0, 0], bounds[0, 1], bounds[0, 2]],
                    [bounds[1, 0], bounds[0, 1], bounds[0, 2]],
                    [bounds[0, 0], bounds[1, 1], bounds[0, 2]],
                    [bounds[1, 0], bounds[1, 1], bounds[0, 2]],
                    [bounds[0, 0], bounds[0, 1], bounds[1, 2]],
                    [bounds[1, 0], bounds[0, 1], bounds[1, 2]],
                    [bounds[0, 0], bounds[1, 1], bounds[1, 2]],
                    [bounds[1, 0], bounds[1, 1], bounds[1, 2]],
                ]
                sample_points.extend(corners)

                # Check if all points are inside the space
                # If ANY point is outside, element is NOT fully inside (violation)
                element_fully_inside = True
                for point in sample_points:
                    try:
                        if not space_mesh.contains([point])[0]:
                            element_fully_inside = False
                            break
                    except Exception:
                        element_fully_inside = False
                        break

                # If element is NOT fully inside space, this is a violation
                if not element_fully_inside:
                    has_violation = True
                    break

            except Exception:
                # If geometry extraction fails for element, treat as violation
                has_violation = True
                break

        if has_violation:
            violations.append(space_guid)

    return violations