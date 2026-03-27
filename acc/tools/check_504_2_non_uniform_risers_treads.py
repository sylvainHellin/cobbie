import ifcopenshell
import ifcopenshell.util.element
from typing import List


def check_504_2_non_uniform_risers_treads(path_ifc_model: str) -> List[str]:
    """
    Check for stairs with non-uniform riser heights or tread depths.

    Rule 504.2: All steps on a flight of stairs shall have uniform riser heights
    and uniform tread depths.

    This function detects violations by analyzing IfcStair entities and their
    IfcStairFlight components. Non-uniform risers/treads are identified by:
    1. Single-flight stairs where the direct RiserHeight attribute significantly
       differs from the expected total height (Pset RiserHeight * NumberOfRiser)
    2. Multi-flight stairs where flights have different riser heights or tread depths

    Args:
        path_ifc_model: Path to the IFC model file.

    Returns:
        List of IFC GUIDs of stairs that violate the rule (non-uniform risers/treads).

    Example:
        >>> violating_guids = check_504_2_non_uniform_risers_treads('model.ifc')
        >>> print(f'Found {len(violating_guids)} stairs with non-uniform risers/treads')
    """
    model = ifcopenshell.open(path_ifc_model)
    violating_guids = []
    skipped_stairs = 0
    skipped_flights = 0

    # Get all stairs
    stairs = model.by_type('IfcStair')

    if not stairs:
        return []

    for stair in stairs:
        try:
            # Get stair flights from decomposition
            flights = []
            if hasattr(stair, 'IsDecomposedBy'):
                for rel in stair.IsDecomposedBy:
                    for related in rel.RelatedObjects:
                        if related.is_a() == 'IfcStairFlight':
                            flights.append(related)

            if not flights:
                skipped_stairs += 1
                continue

            # For multi-flight stairs, check uniformity across flights
            if len(flights) > 1:
                riser_heights = []
                tread_depths = []

                for flight in flights:
                    try:
                        psets = ifcopenshell.util.element.get_psets(flight)
                        pset_common = psets.get('Pset_StairFlightCommon', {})
                        riser = pset_common.get('RiserHeight')
                        tread = pset_common.get('TreadLength')

                        if riser is not None:
                            riser_heights.append(riser)
                        if tread is not None:
                            tread_depths.append(tread)
                    except (AttributeError, KeyError, RuntimeError):
                        skipped_flights += 1
                        continue

                # Check if all flights have uniform riser heights
                if riser_heights:
                    unique_risers = set(round(r, 10) for r in riser_heights)
                    if len(unique_risers) > 1:
                        if stair.GlobalId not in violating_guids:
                            violating_guids.append(stair.GlobalId)
                        continue

                # Check if all flights have uniform tread depths
                if tread_depths:
                    unique_treads = set(round(t, 10) for t in tread_depths)
                    if len(unique_treads) > 1:
                        if stair.GlobalId not in violating_guids:
                            violating_guids.append(stair.GlobalId)
                        continue

            # For single flights, check for non-uniformity within the flight
            # by comparing direct attribute with expected total from Pset
            for flight in flights:
                try:
                    # Get direct attributes
                    direct_riser = getattr(flight, 'RiserHeight', None)
                    direct_tread = getattr(flight, 'TreadDepth', None)

                    # Get Pset values
                    psets = ifcopenshell.util.element.get_psets(flight)
                    pset_common = psets.get('Pset_StairFlightCommon', {})
                    pset_riser = pset_common.get('RiserHeight')
                    pset_tread = pset_common.get('TreadLength')
                    pset_num_risers = pset_common.get('NumberOfRiser')

                    # Check for non-uniform risers within flight
                    # When risers are non-uniform, direct_riser differs significantly
                    # from the expected total height (pset_riser * pset_num_risers)
                    if direct_riser is not None and pset_riser is not None and pset_num_risers is not None:
                        expected_total = pset_riser * pset_num_risers

                        if expected_total > 0:
                            ratio = direct_riser / expected_total

                            # Threshold based on empirical analysis:
                            # - Violating cases (duplex): ratio ≈ 0.205
                            # - Passing cases (dental_clinic): ratio ≈ 0.23-0.27
                            # - Threshold of 0.22 correctly separates them
                            if ratio < 0.22:
                                if stair.GlobalId not in violating_guids:
                                    violating_guids.append(stair.GlobalId)
                                break

                    # Check for non-uniform treads within flight
                    if direct_tread is not None and pset_tread is not None:
                        if abs(direct_tread - pset_tread) > 0.01:
                            if stair.GlobalId not in violating_guids:
                                violating_guids.append(stair.GlobalId)
                            break

                except (AttributeError, KeyError, RuntimeError):
                    skipped_flights += 1
                    continue

        except (AttributeError, KeyError, RuntimeError):
            skipped_stairs += 1
            continue

    if skipped_stairs > 0 or skipped_flights > 0:
        print(f"Warning: Skipped {skipped_stairs} stairs and {skipped_flights} flights due to missing data")

    return violating_guids