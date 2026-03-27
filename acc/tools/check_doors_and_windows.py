import ifcopenshell
import ifcopenshell.util.element
from typing import List, Optional


def check_doors_and_windows(path_ifc_model: str) -> List[str]:
    """Check doors and windows for orphan status and floor mismatch.

    This rule checks that doors and windows in the model are located in the same floor
    as the wall they are related to. The rule also checks that the model doesn't contain
    any orphan doors or windows (a door or a window, which doesn't have a relation to
    any wall).

    Parameters:
        Check Orphan Doors and Windows: True

    Args:
        path_ifc_model: Path to the IFC model file (string).

    Returns:
        List of IFC GUIDs of all elements that violate this rule.
        Returns an empty list if no violations are found.

    Example:
        >>> violations = check_doors_and_windows('/path/to/model.ifc')
        >>> print(f'Found {len(violations)} violations')
        Found 2 violations
        >>> for guid in violations:
        ...     print(guid)
        1hOSvn6df7F8_7GcBWlSFK
        1hOSvn6df7F8_7GcBWlSDm
    """
    model = ifcopenshell.open(path_ifc_model)
    violations = []
    skipped = 0

    def get_related_structure(elem) -> Optional:
        """Find the wall, curtain wall, or roof that a door or window is related to."""
        # Check for traditional wall relationship via FillsVoids
        fills_voids = getattr(elem, 'FillsVoids', None) or []
        for rel in fills_voids:
            opening = rel.RelatingOpeningElement
            voids_rels = getattr(opening, 'VoidsElements', None) or []
            for void_rel in voids_rels:
                return void_rel.RelatingBuildingElement

        # Check for curtain wall or roof relationship via Decomposes
        decomposes = getattr(elem, 'Decomposes', None) or []
        for rel in decomposes:
            relating_obj = getattr(rel, 'RelatingObject', None)
            if relating_obj:
                if relating_obj.is_a('IfcCurtainWall') or relating_obj.is_a('IfcRoof'):
                    return relating_obj

        return None

    def get_building_storey(elem) -> Optional:
        """Get the building storey (floor) for an element."""
        try:
            container = ifcopenshell.util.element.get_container(elem)
            if container and container.is_a('IfcBuildingStorey'):
                return container
        except (AttributeError, RuntimeError):
            pass
        return None

    # Check all doors and windows
    for elem in model.by_type('IfcDoor') + model.by_type('IfcWindow'):
        try:
            guid = getattr(elem, 'GlobalId', None)
            if not guid:
                skipped += 1
                continue

            # Find related structure (wall, curtain wall, or roof)
            structure = get_related_structure(elem)

            # Check if orphan (no related wall/curtain wall/roof)
            if structure is None:
                violations.append(guid)
                continue

            # Check if door/window and structure are in same floor
            elem_storey = get_building_storey(elem)
            structure_storey = get_building_storey(structure)

            if elem_storey and structure_storey:
                if elem_storey.id() != structure_storey.id():
                    violations.append(guid)
            # If one or both have no storey, we don't flag as violation
            # (only floor mismatches and orphans are violations)

        except (AttributeError, KeyError, RuntimeError):
            skipped += 1
            continue

    if skipped > 0:
        print(f'Warning: Skipped {skipped} elements due to errors')

    return violations