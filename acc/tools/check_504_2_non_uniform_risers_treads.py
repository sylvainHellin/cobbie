import ifcopenshell
import ifcopenshell.util.element
import numpy as np
from typing import List


def check_504_2_non_uniform_risers_treads(path_ifc_model: str) -> List[str]:
    """
    Rule: 504.2 Treads and Risers
    All steps on a flight of stairs shall have uniform riser heights and uniform tread depths.

    This function checks if stairs have non-uniform riser heights or tread depths by
    analyzing the geometric representation of stair flights.

    Args:
        path_ifc_model: Path to the IFC model file

    Returns:
        List of IFC GUIDs of stairs that violate the rule (have non-uniform riser heights
        or tread depths)

    Example:
        >>> model_path = "/path/to/model.ifc"
        >>> violations = check_504_2_non_uniform_risers_treads(model_path)
        >>> print(f"Found {len(violations)} stairs with non-uniform risers/treads")
    """
    model = ifcopenshell.open(path_ifc_model)
    violating_guids = []

    # Tolerance for considering values as equal (in meters)
    TOLERANCE = 0.01  # 10mm tolerance
    # Minimum difference to consider (filter out noise/thickness)
    MIN_DIFF = 0.05  # 50mm

    stairs = model.by_type('IfcStair')

    for stair in stairs:
        guid = stair.GlobalId

        # Get all stair flights for this stair
        flights = []
        if stair.IsDecomposedBy:
            for rel in stair.IsDecomposedBy:
                for obj in rel.RelatedObjects:
                    if obj.is_a() == 'IfcStairFlight':
                        flights.append(obj)

        if not flights:
            continue

        has_non_uniform_risers = False
        has_non_uniform_treads = False

        for flight in flights:
            # Analyze geometry from Body representation
            if not flight.Representation or not flight.Representation.Representations:
                continue

            for rep in flight.Representation.Representations:
                if not hasattr(rep, 'RepresentationIdentifier'):
                    continue

                if rep.RepresentationIdentifier != 'Body':
                    continue

                # Extract Z and Y coordinates from IfcExtrudedAreaSolid items
                z_coords = []
                y_coords = []

                for item in rep.Items:
                    if item.is_a() == 'IfcExtrudedAreaSolid':
                        try:
                            if hasattr(item, 'Position') and hasattr(item.Position, 'Location'):
                                coords = item.Position.Location.Coordinates
                                if len(coords) >= 3:
                                    z_coords.append(coords[2])
                                    y_coords.append(coords[1])
                        except (AttributeError, IndexError):
                            continue

                if len(z_coords) < 2:
                    continue

                # Sort coordinates
                z_sorted = sorted(z_coords)
                y_sorted = sorted(y_coords)

                # Calculate all Z differences (riser candidates)
                z_diffs = [z_sorted[i+1] - z_sorted[i] for i in range(len(z_sorted)-1)]

                # Filter out very small differences (likely modeling artifacts)
                large_z_diffs = [d for d in z_diffs if d > MIN_DIFF]

                # Check uniformity of risers
                if len(large_z_diffs) > 1:
                    large_z_diffs_array = np.array(large_z_diffs)
                    median_height = np.median(large_z_diffs_array)

                    # Check for outliers - if any value deviates from median by more than tolerance
                    outliers = [h for h in large_z_diffs if abs(h - median_height) > TOLERANCE]

                    if len(outliers) > 0:
                        has_non_uniform_risers = True

                # Calculate Y differences for tread depths
                y_diffs = [abs(y_sorted[i+1] - y_sorted[i]) for i in range(len(y_sorted)-1)]
                large_y_diffs = [d for d in y_diffs if d > MIN_DIFF]

                if len(large_y_diffs) > 1:
                    large_y_diffs_array = np.array(large_y_diffs)
                    median_depth = np.median(large_y_diffs_array)
                    outliers = [d for d in large_y_diffs if abs(d - median_depth) > TOLERANCE]

                    if len(outliers) > 0:
                        has_non_uniform_treads = True

        if has_non_uniform_risers or has_non_uniform_treads:
            violating_guids.append(guid)

    return violating_guids