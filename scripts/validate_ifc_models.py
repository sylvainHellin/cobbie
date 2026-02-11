"""
Validate all IFC models in src/db/bim_models/ for IFC schema compliance.

Usage:
    uv run scripts/validate_ifc_models.py
    uv run scripts/validate_ifc_models.py --verbose       # Show per-category breakdown
    uv run scripts/validate_ifc_models.py --sort-by issues # Sort by total issues (descending)
    uv run scripts/validate_ifc_models.py --csv            # Also export CSV to outputs/ifc-bench/
    uv run scripts/validate_ifc_models.py --md             # Also export markdown report to outputs/ifc-bench/
"""

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

import ifcopenshell
import ifcopenshell.validate
from tabulate import tabulate

BIM_MODELS_DIR = Path("src/db/bim_models")
OUTPUT_DIR = Path("outputs/ifc-bench")


def validate_model(path: Path) -> dict:
    """Validate a single IFC model and return a summary dict."""
    result: dict = {
        "project": path.parent.name,
        "file": path.name,
        "schema": "",
        "entities": 0,
        "empty_shape_repr": 0,
        "invalid_refs": 0,
        "missing_attrs": 0,
        "other": 0,
        "total_issues": 0,
        "error": None,
    }

    try:
        model = ifcopenshell.open(str(path))
    except Exception as e:
        result["error"] = str(e)
        return result

    result["schema"] = model.schema
    result["entities"] = len(list(model))

    logger = ifcopenshell.validate.json_logger()
    ifcopenshell.validate.validate(model, logger)

    for err in logger.statements:
        msg = str(err.get("message", ""))
        inst = err.get("instance", "")
        entity_type = inst.is_a() if hasattr(inst, "is_a") else ""

        if entity_type == "IfcShapeRepresentation" and "()" in msg:
            result["empty_shape_repr"] += 1
        elif "Not valid" in msg:
            result["invalid_refs"] += 1
        elif "not optional" in msg.lower():
            result["missing_attrs"] += 1
        else:
            result["other"] += 1

    result["total_issues"] = (
        result["empty_shape_repr"]
        + result["invalid_refs"]
        + result["missing_attrs"]
        + result["other"]
    )
    return result


CSV_HEADERS = [
    "project",
    "file",
    "schema",
    "entities",
    "empty_shape_repr",
    "invalid_refs",
    "missing_attrs",
    "other",
    "total_issues",
    "error",
]


def export_csv(results: list[dict]) -> None:
    """Write results to a CSV file in outputs/ifc-bench/."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "ifc_validation.csv"
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for r in results:
            writer.writerow({k: r[k] for k in CSV_HEADERS})
    print(f"CSV exported to {path}")


def export_markdown(
    results: list[dict],
    total_files: int,
    clean: int,
    with_issues: int,
    failed: int,
    total_issues: int,
) -> None:
    """Write a markdown report to outputs/ifc-bench/."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_DIR / "ifc_validation.md"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines: list[str] = []
    lines.append("# IFC Model Validation Report")
    lines.append(f"\nGenerated: {now}\n")
    lines.append("## Summary\n")
    lines.append(f"- **Files validated**: {total_files}")
    lines.append(f"- **Clean (0 issues)**: {clean}")
    lines.append(f"- **With issues**: {with_issues}")
    lines.append(f"- **Failed to open**: {failed}")
    lines.append(f"- **Total issues**: {total_issues}\n")

    # Full table
    lines.append("## Results\n")
    md_headers = [
        "Project",
        "File",
        "Schema",
        "Entities",
        "Empty ShapeRepr",
        "Invalid Refs",
        "Missing Attrs",
        "Other",
        "Total Issues",
    ]
    md_rows = [
        [
            r["project"],
            r["file"],
            r["schema"] or "ERROR",
            r["entities"],
            r["empty_shape_repr"],
            r["invalid_refs"],
            r["missing_attrs"],
            r["other"],
            r["total_issues"],
        ]
        for r in results
    ]
    lines.append(tabulate(md_rows, headers=md_headers, tablefmt="github", numalign="right"))

    # Issue category explanations
    lines.append("\n\n## Issue Categories\n")
    lines.append("| Category | Description |")
    lines.append("|----------|-------------|")
    lines.append("| Empty ShapeRepr | `IfcShapeRepresentation` with empty `Items` set — violates `SET [1:?]` requirement |")
    lines.append("| Invalid Refs | Attributes referencing entities of the wrong type |")
    lines.append("| Missing Attrs | Required (non-optional) attributes set to `$` |")
    lines.append("| Other | Other schema violations |")

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"Markdown report exported to {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate IFC models for schema compliance")
    parser.add_argument(
        "--verbose", action="store_true", help="Show per-category issue breakdown"
    )
    parser.add_argument(
        "--sort-by",
        choices=["project", "issues", "entities"],
        default="project",
        help="Sort results by column (default: project)",
    )
    parser.add_argument("--csv", action="store_true", help="Export CSV to outputs/ifc-bench/")
    parser.add_argument("--md", action="store_true", help="Export markdown report to outputs/ifc-bench/")
    args = parser.parse_args()

    ifc_files = sorted(BIM_MODELS_DIR.rglob("*.ifc"))
    if not ifc_files:
        print("No IFC files found.")
        sys.exit(1)

    print(f"Found {len(ifc_files)} IFC files. Validating...\n")

    results: list[dict] = []
    for i, path in enumerate(ifc_files, 1):
        rel_path = path.relative_to(BIM_MODELS_DIR)
        print(f"  [{i}/{len(ifc_files)}] {rel_path} ... ", end="", flush=True)
        t0 = time.time()
        result = validate_model(path)
        elapsed = time.time() - t0
        if result["error"]:
            print(f"ERROR ({elapsed:.1f}s)")
        else:
            print(f"{result['total_issues']} issues ({elapsed:.1f}s)")
        results.append(result)

    # Sort
    if args.sort_by == "issues":
        results.sort(key=lambda r: r["total_issues"], reverse=True)
    elif args.sort_by == "entities":
        results.sort(key=lambda r: r["entities"], reverse=True)
    else:
        results.sort(key=lambda r: (r["project"], r["file"]))

    # Build table
    if args.verbose:
        headers = [
            "Project",
            "File",
            "Schema",
            "Entities",
            "Empty ShapeRepr",
            "Invalid Refs",
            "Missing Attrs",
            "Other",
            "Total Issues",
        ]
        rows = [
            [
                r["project"],
                r["file"],
                r["schema"] or "ERROR",
                r["entities"],
                r["empty_shape_repr"],
                r["invalid_refs"],
                r["missing_attrs"],
                r["other"],
                r["total_issues"],
            ]
            for r in results
        ]
    else:
        headers = ["Project", "File", "Schema", "Entities", "Total Issues"]
        rows = [
            [
                r["project"],
                r["file"],
                r["schema"] or "ERROR",
                r["entities"],
                r["total_issues"],
            ]
            for r in results
        ]

    print()
    print(tabulate(rows, headers=headers, tablefmt="simple", numalign="right"))

    # Summary
    total_files = len(results)
    failed = sum(1 for r in results if r["error"])
    clean = sum(1 for r in results if not r["error"] and r["total_issues"] == 0)
    with_issues = total_files - clean - failed
    total_issues = sum(r["total_issues"] for r in results)
    summary = f"{total_files} files validated | {clean} clean | {with_issues} with issues | {failed} failed to open | {total_issues} total issues"
    print(f"\n{summary}")

    # CSV export
    if args.csv:
        export_csv(results)

    # Markdown export
    if args.md:
        export_markdown(results, total_files, clean, with_issues, failed, total_issues)


if __name__ == "__main__":
    main()
