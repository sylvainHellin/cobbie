"""Tool for classifying IFC spaces using the model's Space Usage CSV."""

import csv
import re
from pathlib import Path


def _load_patterns(csv_path: Path) -> list[tuple[re.Pattern[str], str]]:
    """Load Space Usage CSV and compile glob patterns into regexes.

    Skips rows where Layer == 'Zones' (zone-level, not space-level).
    Returns list of (compiled_regex, classification_name) in CSV order.
    """
    patterns: list[tuple[re.Pattern[str], str]] = []
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            layer = row.get("Layer", "").strip()
            if layer == "Zones":
                continue

            raw_pattern = row.get("Name", "").strip()
            classification = row.get("Classification Name", "").strip()
            if not raw_pattern or not classification:
                continue

            # Convert glob pattern to regex: escape special chars, then replace * with .*
            escaped = re.escape(raw_pattern).replace(r"\*", ".*")
            regex = re.compile(f"^{escaped}$", re.IGNORECASE)
            patterns.append((regex, classification))

    return patterns


def classify_spaces(
    spaces: list[dict],
    path_ifc_model: str,
) -> list[dict]:
    """Classify IFC spaces using the Space Usage CSV for the given model.

    Loads the 'Space Usage.csv' from the same directory as the IFC model
    and matches each space name against the CSV patterns (glob-style with *).
    First matching pattern wins. Matching is case-insensitive.

    Args:
        spaces: List of dicts, each with at least "guid" and "name" keys.
        path_ifc_model: Path to the IFC model file. The CSV is expected
            in the same directory.

    Returns:
        The same list with a "classification" key added to each dict.
        Value is the matched classification name, or "Unclassified" if
        no pattern matches.

    Example:
        >>> spaces = [
        ...     {"guid": "abc123", "name": "CORRIDOR"},
        ...     {"guid": "def456", "name": "BEDROOM"},
        ... ]
        >>> result = classify_spaces(spaces, "acc/bim_models/duplex/arc.ifc")
        >>> result[0]["classification"]
        'Circulation'
    """
    csv_path = Path(path_ifc_model).parent / "Space Usage.csv"
    if not csv_path.exists():
        # No CSV available — mark all as Unclassified
        for space in spaces:
            space["classification"] = "Unclassified"
        return spaces

    patterns = _load_patterns(csv_path)

    for space in spaces:
        name = space.get("name", "")
        classification = "Unclassified"

        for regex, cls_name in patterns:
            if regex.match(name):
                classification = cls_name
                break

        space["classification"] = classification

    return spaces
