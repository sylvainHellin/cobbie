"""Extract metrics, params, and tags from MLflow runs (including nested) from SQLite.

Outputs hierarchical JSON to stdout or a file.

Usage:
    uv run scripts/extract_mlflow_runs.py -e "ACC_Training_v2"
    uv run scripts/extract_mlflow_runs.py -e "ACC_Training_v2" -n 3
    uv run scripts/extract_mlflow_runs.py --run-id <run_id>
    uv run scripts/extract_mlflow_runs.py -e "ACC_Training_v2" -o output.json
"""

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "acc.sqlite"


def ms_to_iso(ms: int | None) -> str | None:
    if ms is None:
        return None
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def query_key_value_table(
    conn: sqlite3.Connection, table: str, run_uuid: str
) -> dict[str, object]:
    """Query a table with (key, value, run_uuid) structure and return as dict."""
    rows = conn.execute(
        f"SELECT key, value FROM {table} WHERE run_uuid = ?",  # noqa: S608
        (run_uuid,),
    ).fetchall()
    return {k: v for k, v in rows}


def build_run_dict(
    conn: sqlite3.Connection,
    run_row: sqlite3.Row,
    experiment_name: str | None = None,
) -> dict[str, object]:
    run_uuid = run_row["run_uuid"]
    metrics = query_key_value_table(conn, "latest_metrics", run_uuid)
    params = query_key_value_table(conn, "params", run_uuid)
    tags = query_key_value_table(conn, "tags", run_uuid)

    return {
        "run_id": run_uuid,
        "run_name": run_row["name"],
        "experiment": experiment_name,
        "status": run_row["status"],
        "start_time": ms_to_iso(run_row["start_time"]),
        "end_time": ms_to_iso(run_row["end_time"]),
        "metrics": metrics,
        "params": params,
        "tags": tags,
    }


def get_experiment_id(conn: sqlite3.Connection, name: str) -> int:
    row = conn.execute(
        "SELECT experiment_id FROM experiments WHERE name = ?", (name,)
    ).fetchone()
    if row is None:
        print(f"Error: experiment '{name}' not found.", file=sys.stderr)
        sys.exit(1)
    return row["experiment_id"]


def get_parent_runs(
    conn: sqlite3.Connection, experiment_id: int, last_n: int
) -> list[sqlite3.Row]:
    """Get the last N parent runs (runs without mlflow.parentRunId tag)."""
    return conn.execute(
        """
        SELECT r.* FROM runs r
        WHERE r.experiment_id = ?
          AND r.lifecycle_stage = 'active'
          AND NOT EXISTS (
            SELECT 1 FROM tags t
            WHERE t.run_uuid = r.run_uuid AND t.key = 'mlflow.parentRunId'
          )
        ORDER BY r.start_time DESC
        LIMIT ?
        """,
        (experiment_id, last_n),
    ).fetchall()


def get_nested_runs(conn: sqlite3.Connection, parent_run_id: str) -> list[sqlite3.Row]:
    return conn.execute(
        """
        SELECT r.* FROM runs r
        JOIN tags t ON t.run_uuid = r.run_uuid
        WHERE t.key = 'mlflow.parentRunId' AND t.value = ?
          AND r.lifecycle_stage = 'active'
        ORDER BY r.start_time ASC
        """,
        (parent_run_id,),
    ).fetchall()


def extract_runs(
    conn: sqlite3.Connection,
    experiment_name: str | None,
    parent_rows: list[sqlite3.Row],
) -> list[dict[str, object]]:
    results = []
    for row in parent_rows:
        run_dict = build_run_dict(conn, row, experiment_name)
        nested_rows = get_nested_runs(conn, row["run_uuid"])
        run_dict["nested_runs"] = [
            build_run_dict(conn, nr, experiment_name) for nr in nested_rows
        ]
        results.append(run_dict)
    return results


_SPLITS = ("training", "validation", "test")
_SUMMARY_KEYS = ("f1_aggregated", "f1_avg", "precision", "recall", "tp", "fp", "fn")


def _extract_split_metrics(metrics: dict[str, object], split: str) -> dict[str, object] | None:
    """Extract metrics for a single split (training/validation/test).

    Returns None if the split has no metrics at all.
    """
    prefix = f"{split}_"
    out: dict[str, object] = {}
    for key, value in metrics.items():
        if not key.startswith(prefix):
            continue
        short = key[len(prefix) :]
        # Keep the well-known keys + any per-model f1/precision/recall scores
        if short in _SUMMARY_KEYS or short.startswith(("f1_", "precision_", "recall_")):
            out[short] = value
    return out or None


def build_summary(results: list[dict[str, object]]) -> list[dict[str, object]]:
    """Build a flat summary of nested runs that have evaluation metrics."""
    summary: list[dict[str, object]] = []
    for parent in results:
        parent_name = parent.get("run_name", "")
        for nested in parent.get("nested_runs", []):  # type: ignore[union-attr]
            metrics: dict[str, object] = nested.get("metrics", {})
            splits: dict[str, object] = {}
            for split in _SPLITS:
                split_data = _extract_split_metrics(metrics, split)
                if split_data is not None:
                    splits[split] = split_data
            if not splits:
                continue
            summary.append(
                {
                    "run_name": nested.get("run_name"),
                    "parent_run": parent_name,
                    "status": nested.get("status"),
                    **splits,
                }
            )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract MLflow run data from SQLite to JSON."
    )
    parser.add_argument("--experiment", "-e", help="Experiment name")
    parser.add_argument(
        "--last", "-n", type=int, default=1, help="Number of most recent parent runs (default: 1)"
    )
    parser.add_argument("--run-id", help="Specific run ID (bypasses experiment/last)")
    parser.add_argument("--output", "-o", help="Output file path (default: stdout)")
    args = parser.parse_args()

    if not args.experiment and not args.run_id:
        parser.error("Either --experiment or --run-id is required")

    if not DB_PATH.exists():
        print(f"Error: MLflow database not found at {DB_PATH}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    if args.run_id:
        row = conn.execute(
            "SELECT * FROM runs WHERE run_uuid = ?", (args.run_id,)
        ).fetchone()
        if row is None:
            print(f"Error: run '{args.run_id}' not found.", file=sys.stderr)
            sys.exit(1)
        # Look up experiment name
        exp_row = conn.execute(
            "SELECT name FROM experiments WHERE experiment_id = ?",
            (row["experiment_id"],),
        ).fetchone()
        experiment_name = exp_row["name"] if exp_row else None
        results = extract_runs(conn, experiment_name, [row])
    else:
        experiment_id = get_experiment_id(conn, args.experiment)
        parent_rows = get_parent_runs(conn, experiment_id, args.last)
        if not parent_rows:
            print(
                f"Error: no parent runs found in experiment '{args.experiment}'.",
                file=sys.stderr,
            )
            sys.exit(1)
        results = extract_runs(conn, args.experiment, parent_rows)

    conn.close()

    output = json.dumps(results, indent=2, ensure_ascii=False)
    summary = build_summary(results)

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(output + "\n")
        print(f"Written to {out_path}", file=sys.stderr)

        summary_path = out_path.with_name(f"{out_path.stem}_summary{out_path.suffix}")
        summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
        print(f"Summary written to {summary_path}", file=sys.stderr)
    else:
        print(output)


if __name__ == "__main__":
    main()
