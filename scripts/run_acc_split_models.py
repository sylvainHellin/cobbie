"""Split 12 models into train/validate/test sets (4/4/4).

Greedy assignment that maximises issue-coverage across splits,
processing rules from hardest-to-cover first.
"""

import csv
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = REPO_ROOT / "acc" / "res" / "ground_truth_stats.csv"
OUT_PATH = REPO_ROOT / "acc" / "config" / "model_splits.json"
COVERAGE_MATRIX_PATH = REPO_ROOT / "acc" / "config" / "coverage_matrix.csv"
PREFIXED_STATS_PATH = REPO_ROOT / "acc" / "res" / "ground_truth_stats_split.csv"
SPLIT_SIZE = 4
SPLITS = ("train", "validate", "test")


def read_issue_matrix(csv_path: Path) -> tuple[list[str], list[str], dict[str, dict[str, bool]]]:
    """Return (models, rules, has_issues[rule][model])."""
    with open(csv_path) as f:
        reader = csv.reader(f)
        header = next(reader)
        models = header[2:]  # skip rule_code, rule_title

        rules: list[str] = []
        has_issues: dict[str, dict[str, bool]] = {}
        for row in reader:
            if not row or not row[0]:
                continue
            rule = row[1]  # rule_title is the readable name
            rules.append(rule)
            has_issues[rule] = {}
            for model, count_str in zip(models, row[2:]):
                has_issues[rule][model] = int(count_str) > 0

    return models, rules, has_issues


def count_models_with_issues(rule: str, has_issues: dict[str, dict[str, bool]]) -> int:
    return sum(1 for v in has_issues[rule].values() if v)


def greedy_assign(
    models: list[str],
    rules: list[str],
    has_issues: dict[str, dict[str, bool]],
) -> dict[str, list[str]]:
    splits: dict[str, list[str]] = {s: [] for s in SPLITS}
    assigned: set[str] = set()

    # Sort rules by number of models with issues (ascending = hardest first)
    sorted_rules = sorted(rules, key=lambda r: count_models_with_issues(r, has_issues))

    # Track which (rule, split) pairs still need coverage
    uncovered: set[tuple[str, str]] = set()
    for rule in rules:
        for split in SPLITS:
            uncovered.add((rule, split))

    def score_model(model: str) -> int:
        """Count how many uncovered (rule, split) pairs this model could help with."""
        count = 0
        for rule in rules:
            if not has_issues[rule].get(model, False):
                continue
            for split in SPLITS:
                if (rule, split) in uncovered and len(splits[split]) < SPLIT_SIZE and model not in assigned:
                    count += 1
        return count

    for rule in sorted_rules:
        # Which splits lack coverage for this rule?
        lacking = [s for s in SPLITS if (rule, s) in uncovered]
        if not lacking:
            continue

        # Candidate models: unassigned, have issues for this rule
        candidates = [m for m in models if m not in assigned and has_issues[rule].get(m, False)]
        if not candidates:
            continue

        # Priority when fewer candidates than lacking splits: train first, then test
        priority = [s for s in ("train", "test", "validate") if s in lacking]

        for split in priority:
            if len(splits[split]) >= SPLIT_SIZE:
                continue
            if not candidates:
                break

            # Pick model that covers the most other uncovered pairs (tie-break: alphabetical)
            candidates.sort(key=lambda m: (-score_model(m), m))
            chosen = candidates.pop(0)

            splits[split].append(chosen)
            assigned.add(chosen)

            # Mark all (rule, split) pairs now covered by this assignment
            for r in rules:
                if has_issues[r].get(chosen, False) and (r, split) in uncovered:
                    uncovered.discard((r, split))

    # Assign remaining models to smallest splits (target 4/4/4)
    remaining = [m for m in models if m not in assigned]
    remaining.sort()  # deterministic
    for model in remaining:
        # Pick split with fewest members
        target = min(SPLITS, key=lambda s: len(splits[s]))
        splits[target].append(model)

    return splits


def print_coverage_report(
    splits: dict[str, list[str]],
    rules: list[str],
    has_issues: dict[str, dict[str, bool]],
) -> None:
    print(f"\n{'Rule':<45} {'train':>7} {'validate':>9} {'test':>6}")
    print("-" * 70)
    for rule in sorted(rules):
        parts: list[str] = []
        for split in SPLITS:
            covered = any(has_issues[rule].get(m, False) for m in splits[split])
            parts.append("Y" if covered else "-")
        n_models = count_models_with_issues(rule, has_issues)
        print(f"{rule:<45} {parts[0]:>7} {parts[1]:>9} {parts[2]:>6}   ({n_models} models)")

    # Summary
    total = len(rules) * len(SPLITS)
    covered = 0
    for rule in rules:
        for split in SPLITS:
            if any(has_issues[rule].get(m, False) for m in splits[split]):
                covered += 1
    print(f"\nCoverage: {covered}/{total} rule-split pairs")


def save_coverage_matrix(
    splits: dict[str, list[str]],
    rules: list[str],
    has_issues: dict[str, dict[str, bool]],
    out_path: Path,
) -> None:
    """Save the rule × split coverage matrix (Y/-) to CSV."""
    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["rule"] + list(SPLITS))
        for rule in sorted(rules):
            row = [rule]
            for split in SPLITS:
                covered = any(has_issues[rule].get(m, False) for m in splits[split])
                row.append("Y" if covered else "-")
            writer.writerow(row)
    print(f"Coverage matrix written to {out_path}")


def save_prefixed_stats(
    splits: dict[str, list[str]],
    csv_path: Path,
    out_path: Path,
) -> None:
    """Rewrite ground_truth_stats with prefixed model names, sorted by split."""
    model_to_prefix = {}
    for split, models in splits.items():
        for m in models:
            model_to_prefix[m] = f"{split}_{m}"

    with open(csv_path) as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)

    original_models = header[2:]
    # Build (sort_key, original_index, prefixed_name) for ordering
    split_order = {s: i for i, s in enumerate(SPLITS)}
    indexed = []
    for i, m in enumerate(original_models):
        prefix = model_to_prefix.get(m, m)
        split_name = prefix.split("_", 1)[0]
        indexed.append((split_order.get(split_name, 99), prefix, i))
    indexed.sort()

    new_header = header[:2] + [name for _, name, _ in indexed]
    col_order = [idx for _, _, idx in indexed]

    with open(out_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(new_header)
        for row in rows:
            if not row or not row[0]:
                continue
            data_cols = row[2:]
            writer.writerow(row[:2] + [data_cols[i] for i in col_order])
    print(f"Prefixed stats written to {out_path}")


def main() -> None:
    models, rules, has_issues = read_issue_matrix(CSV_PATH)
    splits = greedy_assign(models, rules, has_issues)

    # Sort models within each split for readability
    for s in splits:
        splits[s].sort()

    print("Model splits:")
    for name, members in splits.items():
        print(f"  {name}: {members}")

    print_coverage_report(splits, rules, has_issues)

    COVERAGE_MATRIX_PATH.parent.mkdir(parents=True, exist_ok=True)
    save_coverage_matrix(splits, rules, has_issues, COVERAGE_MATRIX_PATH)
    save_prefixed_stats(splits, CSV_PATH, PREFIXED_STATS_PATH)

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w") as f:
        json.dump(splits, f, indent=2)
        f.write("\n")
    print(f"\nWritten to {OUT_PATH}")


if __name__ == "__main__":
    main()
