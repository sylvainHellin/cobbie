import ifcopenshell
import ifcopenshell.util.element
from typing import List
from src.tools.initial import classify_spaces


def check_large_spaces_more_than_one_door(path_ifc_model: str) -> List[str]:
    """
    Check if large spaces (Area ≥ 50.0) have at least 2 doors.

    Large spaces must have at least 2 doors. Spaces with specific usage types
    (Outdoor Space, Parking, Terrace) are excluded from the check.
    Doors identified as 'Hatch' are excluded from the door count.

    Args:
        path_ifc_model: Path to the IFC model file.

    Returns:
        List of IFC GUIDs of spaces that violate the rule (large spaces with
        fewer than 2 non-hatch doors).

    Example:
        >>> path = '/path/to/model.ifc'
        >>> violations = check_large_spaces_more_than_one_door(path)
        >>> print(f'Found {len(violations)} violating spaces')
    """
    # Validate input
    if not path_ifc_model:
        return []

    # Open the IFC model
    try:
        model = ifcopenshell.open(path_ifc_model)
    except (FileNotFoundError, RuntimeError, IOError):
        return []

    # Get all spaces
    spaces = model.by_type('IfcSpace')
    if not spaces:
        return []

    # Excluded space classifications
    excluded_classifications = {'Outdoor Space', 'Parking', 'Terrace'}

    # Prepare space data for classification
    spaces_data = []
    for space in spaces:
        name = getattr(space, 'LongName', None) or getattr(space, 'Name', '')
        spaces_data.append({
            'guid': getattr(space, 'GlobalId', ''),
            'name': name
        })

    # Classify spaces using the model's classification CSV
    try:
        classified_spaces = classify_spaces(spaces_data, path_ifc_model)
    except (FileNotFoundError, RuntimeError, KeyError):
        # If classification fails, proceed with 'Unclassified' for all
        classified_spaces = [{**s, 'classification': 'Unclassified'} for s in spaces_data]

    # Create mapping from GUID to classification
    classification_map = {s['guid']: s.get('classification', 'Unclassified')
                          for s in classified_spaces}

    violations = []
    skipped_area = 0
    skipped_classification = 0

    for space in spaces:
        guid = getattr(space, 'GlobalId', None)
        if not guid:
            continue

        classification = classification_map.get(guid, 'Unclassified')

        # Skip excluded classifications
        if classification in excluded_classifications:
            skipped_classification += 1
            continue

        # Get space area from property sets
        psets = ifcopenshell.util.element.get_psets(space)
        area = None

        for pset_name, pset in psets.items():
            if 'Area' in pset:
                area = pset['Area']
                break

        # Skip if no area found or area < 50.0
        if area is None:
            skipped_area += 1
            continue

        if area < 50.0:
            skipped_area += 1
            continue

        # Count doors for this space (excluding hatches)
        door_count = 0

        if hasattr(space, 'BoundedBy'):
            for rel in space.BoundedBy:
                if hasattr(rel, 'RelatedBuildingElement'):
                    elem = rel.RelatedBuildingElement
                    if elem and elem.is_a() == 'IfcDoor':
                        # Check if this is a hatch door
                        door_name = (getattr(elem, 'Name', '') or '').lower()
                        obj_type = (getattr(elem, 'ObjectType', '') or '').lower()

                        # Exclude doors with 'Hatch' in name or type
                        if 'hatch' in door_name or 'hatch' in obj_type:
                            continue

                        door_count += 1

        # Check if violation (less than 2 doors)
        if door_count < 2:
            violations.append(guid)

    # Optional: Log skipped elements for debugging
    if skipped_area > 0 or skipped_classification > 0:
        print(f"Warning: Skipped {skipped_area} spaces with missing/small area, "
              f"{skipped_classification} spaces with excluded classifications")

    return violations