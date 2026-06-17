"""Extract ifc-bench v2 benchmark statistics from the SQLite database.

Produces:
  - outputs/ifc-bench/benchmark_stats.json  (summary)
  - outputs/ifc-bench/benchmark_category_distribution.csv
  - outputs/ifc-bench/benchmark_project_distribution.csv

Usage:
    uv run scripts/extract_benchmark_stats.py
"""

import csv
import json
from collections import Counter
from pathlib import Path

from src.db.load_dataset import TESTSET, TRAINSET, load_train_test_split
from src.db.query import get_dataset

OUTPUT_DIR = Path("outputs/ifc-bench")

CATEGORY_NAMES = {
    1: "Direct Property",
    2: "Aggregation",
    3: "Computation",
    4: "Estimation/Unavailable",
}


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    full_dataset = get_dataset()
    train_data = TRAINSET
    test_data = TESTSET

    total = len(full_dataset)
    train_size = len(train_data)
    test_size = len(test_data)

    # Category distribution (full dataset)
    cat_counts: Counter[int | None] = Counter(q.category for q in full_dataset)

    # Project distribution (full dataset) — need ifc model info
    # Reload with ifc model data
    _, _ = load_train_test_split()  # ensures models are loaded
    project_questions: dict[str, dict] = {}
    unique_model_ids: set[int] = set()

    for q in full_dataset:
        # Find project info by joining with ifc model
        # Use the ifc relationship from train/dev data which has it populated
        ifc_obj = None
        for item in train_data + test_data:
            if item.id == q.id:
                ifc_obj = item.ifc
                break

        project = ifc_obj.project_name if ifc_obj else "unknown"
        model_name = ifc_obj.model_name if ifc_obj else "unknown"
        model_id = q.ifc_id
        unique_model_ids.add(model_id)

        if project not in project_questions:
            project_questions[project] = {
                "project_name": project,
                "model_names": set(),
                "total": 0,
                "cat_1": 0,
                "cat_2": 0,
                "cat_3": 0,
                "cat_4": 0,
            }
        project_questions[project]["model_names"].add(model_name)
        project_questions[project]["total"] += 1
        cat_key = f"cat_{q.category}" if q.category else "cat_unknown"
        if cat_key in project_questions[project]:
            project_questions[project][cat_key] += 1

    unique_projects = len(project_questions)

    # --- Write summary JSON ---
    stats = {
        "total_qa_pairs": total,
        "total_ifc_models": len(unique_model_ids),
        "total_projects": unique_projects,
        "train_size": train_size,
        "test_size": test_size,
        "split_fraction": 0.5,
        "split_seed": 42,
        "dev_projects_for_manual_tools": ["duplex", "dental_clinic"],
        "categories": {
            f"{cat}_{CATEGORY_NAMES.get(cat, 'unknown') if cat is not None else 'unknown'}": count
            for cat, count in sorted(cat_counts.items(), key=lambda x: (x[0] is None, x[0]))
        },
    }

    stats_path = OUTPUT_DIR / "benchmark_stats.json"
    with open(stats_path, "w") as f:
        json.dump(stats, f, indent=2)
    print(f"Wrote {stats_path}")

    # --- Write category distribution CSV ---
    cat_csv_path = OUTPUT_DIR / "benchmark_category_distribution.csv"
    with open(cat_csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["category", "category_name", "count", "percentage"])
        for cat in sorted(cat_counts.keys(), key=lambda x: (x is None, x)):
            count = cat_counts[cat]
            pct = round(100 * count / total, 1)
            name = CATEGORY_NAMES.get(cat, "Unknown") if cat else "Unknown"
            writer.writerow([cat, name, count, pct])
    print(f"Wrote {cat_csv_path}")

    # --- Write project distribution CSV ---
    proj_csv_path = OUTPUT_DIR / "benchmark_project_distribution.csv"
    with open(proj_csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "project_name",
            "num_models",
            "total_questions",
            "cat_1_direct_property",
            "cat_2_aggregation",
            "cat_3_computation",
            "cat_4_estimation",
        ])
        for project in sorted(project_questions.keys()):
            pq = project_questions[project]
            writer.writerow([
                project,
                len(pq["model_names"]),
                pq["total"],
                pq["cat_1"],
                pq["cat_2"],
                pq["cat_3"],
                pq["cat_4"],
            ])
    print(f"Wrote {proj_csv_path}")

    # --- Print summary ---
    print("\n--- ifc-bench v2 Summary ---")
    print(f"Total QA pairs: {total}")
    print(f"Train / Test: {train_size} / {test_size}")
    print(f"Projects: {unique_projects}")
    print(f"Unique IFC models: {len(unique_model_ids)}")
    print(f"Categories: {dict(sorted(cat_counts.items(), key=lambda x: (x[0] is None, x[0])))}")


if __name__ == "__main__":
    main()
