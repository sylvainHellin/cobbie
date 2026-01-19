"""
IFC Model Summary Extraction for Baseline QA System.

Extracts structured summaries from IFC models with caching support.
Summaries are limited to ~16384 tokens for LLM context windows.
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import ifcopenshell
import ifcopenshell.util.element
from loguru import logger

from src.config import ROOT_PATH

# Cache directory for model summaries
CACHE_DIR = Path(ROOT_PATH) / "analysis" / "data" / "baseline_cache"

# Approximate token limit (using ~4 chars per token estimate)
MAX_TOKENS = 16384
CHARS_PER_TOKEN = 4
MAX_CHARS = MAX_TOKENS * CHARS_PER_TOKEN


def _compute_cache_key(ifc_path: str) -> str:
    """Compute cache key from file path and modification time."""
    path_obj = Path(ifc_path)
    mtime = path_obj.stat().st_mtime
    key_string = f"{ifc_path}:{mtime}"
    return hashlib.md5(key_string.encode()).hexdigest()


def _load_cached_summary(cache_key: str) -> str | None:
    """Load cached summary if it exists."""
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if cache_file.exists():
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("summary")
    return None


def _save_summary_to_cache(cache_key: str, summary: str) -> None:
    """Save summary to cache."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_file = CACHE_DIR / f"{cache_key}.json"
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump({"summary": summary}, f, indent=2)


def extract_model_summary(model_path: str) -> dict[str, Any]:
    """
    Extract structured summary from IFC model.

    Args:
        model_path: Path to the IFC file

    Returns:
        Dictionary containing model summary data
    """
    ifc_file = ifcopenshell.open(model_path)

    summary: dict[str, Any] = {
        "project": {},
        "building": {},
        "storeys": [],
        "spaces": [],
        "element_counts": {},
        "element_types": {},  # NEW: types with dimensions
        "materials": {},
        "properties": {},
    }

    # Extract project info
    projects = ifc_file.by_type("IfcProject")
    if projects:
        project = projects[0]
        summary["project"] = {
            "name": project.Name or "Unnamed Project",
            "description": project.Description or "",
        }

    # Extract building info
    buildings = ifc_file.by_type("IfcBuilding")
    if buildings:
        building = buildings[0]
        summary["building"] = {
            "name": building.Name or "Unnamed Building",
            "description": building.Description or "",
        }

    # Extract storeys
    storeys = ifc_file.by_type("IfcBuildingStorey")
    for storey in storeys:
        elevation = getattr(storey, "Elevation", None)
        summary["storeys"].append({
            "name": storey.Name or "Unnamed Storey",
            "elevation": elevation,
        })

    # Extract spaces (rooms)
    spaces = ifc_file.by_type("IfcSpace")
    for space in spaces[:50]:  # Limit to 50 spaces to control token usage
        space_info: dict[str, Any] = {
            "name": space.Name or "Unnamed Space",
            "long_name": getattr(space, "LongName", None),
        }
        summary["spaces"].append(space_info)

    if len(spaces) > 50:
        summary["spaces_note"] = f"Showing 50 of {len(spaces)} total spaces"

    # Count building elements
    element_types = [
        "IfcWall",
        "IfcWallStandardCase",
        "IfcDoor",
        "IfcWindow",
        "IfcSlab",
        "IfcColumn",
        "IfcBeam",
        "IfcStair",
        "IfcRoof",
        "IfcCurtainWall",
        "IfcRailing",
        "IfcRamp",
        "IfcFurniture",
        "IfcFlowTerminal",
        "IfcDistributionElement",
        "IfcOpeningElement",
        "IfcSpace",
        "IfcCovering",
        "IfcPlate",
        "IfcMember",
    ]

    for element_type in element_types:
        try:
            elements = ifc_file.by_type(element_type)
            if elements:
                summary["element_counts"][element_type] = len(elements)
        except RuntimeError:
            # Entity type not available in this IFC schema version
            pass

    # Extract materials with usage counts
    material_counts: dict[str, int] = {}
    for rel in ifc_file.by_type("IfcRelAssociatesMaterial"):
        material = rel.RelatingMaterial
        material_name = _get_material_name(material)
        if material_name:
            material_counts[material_name] = material_counts.get(material_name, 0) + len(
                rel.RelatedObjects
            )

    # Limit materials to top 20 by usage
    sorted_materials = sorted(material_counts.items(), key=lambda x: x[1], reverse=True)
    summary["materials"] = dict(sorted_materials[:20])
    if len(sorted_materials) > 20:
        summary["materials_note"] = (
            f"Showing top 20 of {len(sorted_materials)} total materials"
        )

    # Extract property summary (fire rating, thermal properties, etc.)
    properties_of_interest = [
        "FireRating",
        "ThermalTransmittance",
        "LoadBearing",
        "IsExternal",
        "AcousticRating",
    ]

    for prop_name in properties_of_interest:
        values = _collect_property_values(ifc_file, prop_name)
        if values:
            summary["properties"][prop_name] = values

    # Extract element types with dimensions
    summary["element_types"] = _extract_element_types_with_dimensions(ifc_file)

    return summary


def _get_material_name(material: Any) -> str | None:
    """Extract material name from various IFC material types."""
    if material is None:
        return None

    # Handle different material types
    if hasattr(material, "Name") and material.Name:
        return material.Name

    if hasattr(material, "ForLayerSet"):
        layer_set = material.ForLayerSet
        if hasattr(layer_set, "LayerSetName") and layer_set.LayerSetName:
            return layer_set.LayerSetName
        if hasattr(layer_set, "MaterialLayers"):
            names = []
            for layer in layer_set.MaterialLayers[:3]:  # Limit layers
                if hasattr(layer, "Material") and layer.Material:
                    if hasattr(layer.Material, "Name") and layer.Material.Name:
                        names.append(layer.Material.Name)
            if names:
                return " / ".join(names)

    if hasattr(material, "Materials"):
        names = []
        for mat in material.Materials[:3]:  # Limit materials
            if hasattr(mat, "Name") and mat.Name:
                names.append(mat.Name)
        if names:
            return " / ".join(names)

    return None


def _collect_property_values(
    ifc_file: ifcopenshell.file, prop_name: str
) -> dict[str, int]:
    """Collect unique values and counts for a property across all elements."""
    value_counts: dict[str, int] = {}

    for pset in ifc_file.by_type("IfcPropertySet"):
        if not hasattr(pset, "HasProperties"):
            continue
        for prop in pset.HasProperties:
            if hasattr(prop, "Name") and prop.Name == prop_name:
                value = _get_property_value(prop)
                if value is not None:
                    value_str = str(value)
                    value_counts[value_str] = value_counts.get(value_str, 0) + 1

    return value_counts


def _get_property_value(prop: Any) -> Any:
    """Extract value from an IFC property."""
    if hasattr(prop, "NominalValue") and prop.NominalValue:
        return prop.NominalValue.wrappedValue
    return None


def _extract_element_types_with_dimensions(
    ifc_file: ifcopenshell.file,
) -> dict[str, list[dict[str, Any]]]:
    """
    Extract element types (e.g., DoorType, WindowType) with their dimensions.

    Returns:
        Dictionary mapping type category to list of types with dimensions
    """
    type_info: dict[str, list[dict[str, Any]]] = {}

    # Element type classes to extract
    type_classes = [
        "IfcDoorType",
        "IfcDoorStyle",  # IFC2X3
        "IfcWindowType",
        "IfcWindowStyle",  # IFC2X3
        "IfcWallType",
        "IfcSlabType",
        "IfcColumnType",
        "IfcBeamType",
        "IfcCoveringType",
        "IfcStairType",
        "IfcRailingType",
        "IfcRoofType",
    ]

    for type_class in type_classes:
        try:
            types = ifc_file.by_type(type_class)
            if not types:
                continue

            category = type_class.replace("Ifc", "").replace("Style", "Type")
            type_info[category] = []

            for element_type in types:
                type_data: dict[str, Any] = {
                    "name": element_type.Name or "Unnamed",
                }

                # Count instances of this type
                try:
                    instances = ifcopenshell.util.element.get_types(element_type)
                    if instances:
                        type_data["instance_count"] = len(instances)
                except Exception:
                    pass

                # Extract dimensions from properties
                dimensions = _extract_type_dimensions(ifc_file, element_type)
                if dimensions:
                    type_data.update(dimensions)

                type_info[category].append(type_data)

        except RuntimeError:
            # Type not available in this IFC schema
            pass

    return type_info


def _extract_type_dimensions(
    ifc_file: ifcopenshell.file, element_type: Any
) -> dict[str, Any]:
    """Extract dimensions from an element type's properties."""
    dimensions: dict[str, Any] = {}

    # Properties to look for (common dimension properties)
    dimension_props = [
        "Width",
        "Height",
        "Depth",
        "Length",
        "Thickness",
        "OverallWidth",
        "OverallHeight",
        "OverallDepth",
        "NominalWidth",
        "NominalHeight",
        "NominalLength",
    ]

    # Get property sets associated with this type
    try:
        psets = ifcopenshell.util.element.get_psets(element_type)
        for pset_name, props in psets.items():
            if isinstance(props, dict):
                for prop_name, value in props.items():
                    # Check if this is a dimension property
                    for dim_prop in dimension_props:
                        if dim_prop.lower() in prop_name.lower():
                            if value is not None and value != "":
                                # Format the value (convert to mm if it looks like meters)
                                if isinstance(value, (int, float)):
                                    # Assume values < 10 are in meters, convert to mm
                                    if value < 10 and value > 0:
                                        dimensions[prop_name] = f"{value * 1000:.0f}mm"
                                    else:
                                        dimensions[prop_name] = f"{value:.0f}mm"
                                else:
                                    dimensions[prop_name] = str(value)
                            break
    except Exception:
        pass

    # Also check for IfcDoorLiningProperties, IfcWindowLiningProperties
    try:
        if hasattr(element_type, "HasPropertySets"):
            for rel in element_type.HasPropertySets or []:
                if hasattr(rel, "is_a"):
                    if rel.is_a("IfcDoorLiningProperties"):
                        if hasattr(rel, "LiningDepth") and rel.LiningDepth:
                            dimensions["LiningDepth"] = f"{rel.LiningDepth * 1000:.0f}mm"
                        if hasattr(rel, "LiningThickness") and rel.LiningThickness:
                            dimensions["LiningThickness"] = f"{rel.LiningThickness * 1000:.0f}mm"
                    elif rel.is_a("IfcWindowLiningProperties"):
                        if hasattr(rel, "LiningDepth") and rel.LiningDepth:
                            dimensions["LiningDepth"] = f"{rel.LiningDepth * 1000:.0f}mm"
    except Exception:
        pass

    return dimensions


def format_summary_for_llm(
    summary: dict[str, Any], filename: str, max_chars: int = MAX_CHARS
) -> str:
    """
    Format summary for LLM, truncating if needed to stay under token limit.

    Args:
        summary: Dictionary containing model summary
        filename: Name of the IFC file
        max_chars: Maximum characters (defaults to ~16384 tokens worth)

    Returns:
        Formatted string for LLM context
    """
    lines: list[str] = []

    # Header
    lines.append(f"# IFC Model Summary: {filename}")
    lines.append("")

    # Project info
    if summary.get("project"):
        lines.append("## Project Information")
        lines.append(f"- Name: {summary['project'].get('name', 'N/A')}")
        if summary["project"].get("description"):
            lines.append(f"- Description: {summary['project']['description']}")
        lines.append("")

    # Building info
    if summary.get("building"):
        lines.append("## Building Information")
        lines.append(f"- Name: {summary['building'].get('name', 'N/A')}")
        if summary["building"].get("description"):
            lines.append(f"- Description: {summary['building']['description']}")
        lines.append("")

    # Element counts (always include, most useful for Category 2 questions)
    if summary.get("element_counts"):
        lines.append("## Element Counts")
        for elem_type, count in sorted(summary["element_counts"].items()):
            lines.append(f"- {elem_type}: {count}")
        lines.append("")

    # Element types with dimensions
    if summary.get("element_types"):
        lines.append("## Element Types with Dimensions")
        for category, types_list in sorted(summary["element_types"].items()):
            if types_list:
                lines.append(f"### {category}")
                for type_data in types_list:
                    name = type_data.get("name", "Unnamed")
                    count = type_data.get("instance_count", 0)
                    # Build dimension string
                    dim_parts = []
                    for key, value in type_data.items():
                        if key not in ("name", "instance_count"):
                            dim_parts.append(f"{key}: {value}")
                    dim_str = ", ".join(dim_parts) if dim_parts else "no dimensions"
                    lines.append(f"- {name} ({count} instances): {dim_str}")
        lines.append("")

    # Storeys
    if summary.get("storeys"):
        lines.append("## Building Storeys")
        for storey in summary["storeys"]:
            elev_str = (
                f" (elevation: {storey['elevation']}m)"
                if storey.get("elevation") is not None
                else ""
            )
            lines.append(f"- {storey['name']}{elev_str}")
        lines.append("")

    # Materials
    if summary.get("materials"):
        lines.append("## Materials (by usage count)")
        for material, count in list(summary["materials"].items())[:15]:
            lines.append(f"- {material}: {count} elements")
        if summary.get("materials_note"):
            lines.append(f"Note: {summary['materials_note']}")
        lines.append("")

    # Spaces (rooms)
    current_text = "\n".join(lines)
    remaining_chars = max_chars - len(current_text) - 500  # Reserve space for footer

    if summary.get("spaces") and remaining_chars > 500:
        lines.append("## Spaces (Rooms)")
        space_lines: list[str] = []
        for space in summary["spaces"]:
            name = space.get("name", "Unnamed")
            long_name = space.get("long_name")
            space_str = f"- {name}"
            if long_name:
                space_str += f" ({long_name})"
            space_lines.append(space_str)

            # Check if we're exceeding limit
            if len("\n".join(space_lines)) > remaining_chars - 200:
                space_lines.append("... (truncated for token limit)")
                break

        lines.extend(space_lines)
        if summary.get("spaces_note"):
            lines.append(f"Note: {summary['spaces_note']}")
        lines.append("")

    # Properties
    if summary.get("properties"):
        lines.append("## Property Summary")
        for prop_name, values in summary["properties"].items():
            if isinstance(values, dict):
                value_str = ", ".join(
                    f"{v}: {c}" for v, c in list(values.items())[:5]
                )
                lines.append(f"- {prop_name}: {value_str}")
        lines.append("")

    result = "\n".join(lines)

    # Final truncation check
    if len(result) > max_chars:
        result = result[: max_chars - 50] + "\n\n... (truncated for token limit)"

    return result


def get_or_create_summary(ifc_path: str, use_cache: bool = True) -> str:
    """
    Get cached summary or create and cache new one.

    Args:
        ifc_path: Path to the IFC file
        use_cache: Whether to use caching (default True)

    Returns:
        Formatted summary string ready for LLM
    """
    # Compute cache key
    cache_key = _compute_cache_key(ifc_path)

    # Try to load from cache
    if use_cache:
        cached = _load_cached_summary(cache_key)
        if cached:
            logger.debug(f"Loaded cached summary for {ifc_path}")
            return cached

    # Extract and format summary
    logger.info(f"Extracting summary from {ifc_path}")
    summary = extract_model_summary(ifc_path)
    filename = os.path.basename(ifc_path)
    formatted = format_summary_for_llm(summary, filename)

    # Cache the result
    if use_cache:
        _save_summary_to_cache(cache_key, formatted)
        logger.debug(f"Cached summary for {ifc_path}")

    return formatted


if __name__ == "__main__":
    # Test on a sample IFC file
    from src.config import TEST_IFC_PATH

    summary = get_or_create_summary(TEST_IFC_PATH, use_cache=False)
    print(summary)
    print(f"\n--- Summary length: {len(summary)} chars (~{len(summary)//4} tokens) ---")
