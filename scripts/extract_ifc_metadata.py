"""Extract IFC model metadata for each file in src/db/bim_models/.

Produces a CSV with per-file metadata including authoring tool, schema version,
element/relationship counts, file size, building type, and validation results.

Usage:
    uv run scripts/extract_ifc_metadata.py
"""

import csv
import sys
import time
from pathlib import Path

import ifcopenshell

BIM_MODELS_DIR = Path("src/db/bim_models")
VALIDATION_CSV = Path("outputs/ifc-bench/ifc_validation.csv")
OUTPUT_DIR = Path("outputs/ifc-bench")
OUTPUT_CSV = OUTPUT_DIR / "ifc_model_metadata.csv"

COLUMNS = [
    "project_name",
    "file_name",
    "authoring_tool",
    "ifc_schema_version",
    "building_type",
    "element_count",
    "relationship_count",
    "file_size_mb",
    "language",
    "total_issues",
    "issue_details",
    "error",
]


def load_validation_data() -> dict[tuple[str, str], dict]:
    """Load existing validation CSV into a lookup dict keyed by (project, file)."""
    if not VALIDATION_CSV.exists():
        print(f"Warning: {VALIDATION_CSV} not found, skipping validation merge.")
        return {}

    lookup: dict[tuple[str, str], dict] = {}
    with open(VALIDATION_CSV) as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row["project"], row["file"])
            lookup[key] = row
    return lookup


def load_model_cards() -> dict[str, dict]:
    """Load model_card.csv from each project directory."""
    cards: dict[str, dict] = {}
    for card_path in BIM_MODELS_DIR.rglob("model_card.csv"):
        project = card_path.parent.name
        try:
            with open(card_path, encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    cards[project] = row
                    break  # Only one row per model_card
        except Exception as e:
            print(f"  Warning: could not read {card_path}: {e}")
    return cards


def extract_authoring_tool(model: ifcopenshell.file) -> str:
    """Extract authoring tool from IfcApplication entities or file header."""
    # Try IfcApplication entities first
    apps = model.by_type("IfcApplication")
    if apps:
        app = apps[0]
        name = getattr(app, "ApplicationFullName", "") or ""
        version = getattr(app, "Version", "") or ""
        if name:
            return f"{name} {version}".strip()

    # Fall back to FILE_NAME header originating_system
    try:
        header = model.header
        file_name = header.file_name
        originating_system = file_name.originating_system
        if originating_system:
            return originating_system
    except (AttributeError, RuntimeError):
        pass

    return ""


def extract_metadata(path: Path) -> dict:
    """Extract all metadata for a single IFC file."""
    row: dict = {col: "" for col in COLUMNS}
    row["project_name"] = path.parent.name
    row["file_name"] = path.name
    row["file_size_mb"] = round(path.stat().st_size / 1_000_000, 2)

    try:
        model = ifcopenshell.open(str(path))
    except Exception as e:
        row["error"] = str(e)
        return row

    row["ifc_schema_version"] = model.schema
    row["authoring_tool"] = extract_authoring_tool(model)
    row["element_count"] = len(model.by_type("IfcProduct"))
    row["relationship_count"] = len(model.by_type("IfcRelationship"))

    return row


def merge_validation(row: dict, validation: dict[tuple[str, str], dict]) -> None:
    """Merge validation data into the row."""
    key = (row["project_name"], row["file_name"])
    val = validation.get(key)
    if not val:
        return

    row["total_issues"] = val.get("total_issues", "")

    # Build issue_details from non-zero categories
    details = []
    for cat in ["empty_shape_repr", "invalid_refs", "missing_attrs", "other"]:
        count = int(val.get(cat, 0))
        if count > 0:
            details.append(f"{cat}={count}")
    row["issue_details"] = "; ".join(details)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    ifc_files = sorted(BIM_MODELS_DIR.rglob("*.ifc"))
    if not ifc_files:
        print("No IFC files found.")
        sys.exit(1)

    print(f"Found {len(ifc_files)} IFC files.\n")

    validation = load_validation_data()
    model_cards = load_model_cards()

    rows: list[dict] = []
    for i, path in enumerate(ifc_files, 1):
        rel = path.relative_to(BIM_MODELS_DIR)
        print(f"  [{i}/{len(ifc_files)}] {rel} ... ", end="", flush=True)

        t0 = time.time()
        row = extract_metadata(path)
        elapsed = time.time() - t0

        # Merge model_card building_type
        card = model_cards.get(row["project_name"])
        if card:
            row["building_type"] = card.get("usage", "")

        # Merge validation
        merge_validation(row, validation)

        status = f"error: {row['error']}" if row["error"] else "ok"
        print(f"{status} ({elapsed:.1f}s)")
        rows.append(row)

    # Sort by project, then file
    rows.sort(key=lambda r: (r["project_name"], r["file_name"]))

    # Write CSV
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} rows to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
