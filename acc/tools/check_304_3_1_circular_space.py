import ifcopenshell
import ifcopenshell.geom
import numpy as np
import trimesh
from typing import List


def check_304_3_1_circular_space(path_ifc_model: str) -> List[str]:
    """
    Check if spaces have enough circular space for wheelchair turning.

    Rule 304.3.1: Circular space shall have a diameter of 1.52 m (60 inches) minimum.

    Applicable Space Classifications: Balcony, Circulation, Garage, Habitable,
    Institutional, Lobby, Mercantile, Office, Parking, Production, Refuge,
    Stair Hall, Workplace

    Args:
        path_ifc_model: Path to the IFC model file.

    Returns:
        List of IFC GUIDs of spaces that violate the rule (do not have enough
        room for wheelchair turning space with the required 1.52m diameter).

    Example:
        >>> violations = check_304_3_1_circular_space('/path/to/model.ifc')
        >>> print(f"Found {len(violations)} violations")
    """
    # Applicable space classifications per the rule
    applicable_classifications = {
        'Balcony', 'Circulation', 'Garage', 'Habitable', 'Institutional',
        'Lobby', 'Mercantile', 'Office', 'Parking', 'Production',
        'Refuge', 'Stair Hall', 'Workplace'
    }

    # Required minimum diameter in meters
    min_required_diameter = 1.52

    # Open the IFC model
    model = ifcopenshell.open(path_ifc_model)

    # Get all IfcSpace elements
    spaces = model.by_type('IfcSpace')
    if not spaces:
        return []

    # Prepare space data for classification
    spaces_data = []
    for space in spaces:
        name = getattr(space, 'LongName', None) or getattr(space, 'Name', '') or ''
        spaces_data.append({
            'guid': space.GlobalId,
            'name': name
        })

    # Classify spaces using the model's Space Usage CSV
    classified_spaces = classify_spaces(spaces_data, path_ifc_model)

    # Build a mapping from guid to classification for quick lookup
    space_classification = {s['guid']: s['classification'] for s in classified_spaces}

    # Track violations and processing statistics
    violating_guids = []
    skipped_count = 0
    processed_count = 0

    # Geometry settings
    settings = ifcopenshell.geom.settings()
    settings.set('context-types', ['Body'])

    # Check each applicable space
    for space in spaces:
        guid = space.GlobalId
        classification = space_classification.get(guid, 'Unclassified')

        # Skip spaces that are not in applicable classifications
        if classification not in applicable_classifications:
            continue

        try:
            # Create geometry shape for the space
            shape = ifcopenshell.geom.create_shape(settings, space)
            verts = shape.geometry.verts
            faces = shape.geometry.faces

            # Create trimesh from the geometry
            mesh = trimesh.Trimesh(
                vertices=np.array(verts).reshape(-1, 3),
                faces=np.array(faces).reshape(-1, 3)
            )

            # Calculate maximum possible circle diameter
            # Use the minimum of X and Y extents as a conservative estimate
            # of the maximum diameter that can fit in the space
            max_diameter = min(mesh.extents[0], mesh.extents[1])

            processed_count += 1

            # Check if space violates the minimum diameter requirement
            if max_diameter < min_required_diameter:
                violating_guids.append(guid)

        except (AttributeError, RuntimeError, ValueError) as e:
            # Skip spaces with geometry processing errors
            skipped_count += 1
            continue

    # Report skipped elements if any
    if skipped_count > 0:
        print(f"Warning: Skipped {skipped_count} spaces due to geometry processing errors")

    return violating_guids