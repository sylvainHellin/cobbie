"""Extract execution traces from MLflow for qualitative analysis.

Identifies questions where the dynamic system (dynamic-None-doc) succeeds
but the static baseline (static-None) fails, then extracts the full
iteration-by-iteration trace for each candidate.

Requires a running MLflow server.

Usage:
    uv run scripts/extract_execution_traces.py
    uv run scripts/extract_execution_traces.py --max-candidates 5
"""

import argparse
import csv
import json
import signal
import warnings
from pathlib import Path

import mlflow
from mlflow import MlflowClient
from mlflow.entities import Trace

from src.analysis.data_extraction import (
    extract_run_data,
    fetch_nested_runs,
)
from src.config import MLFLOW_URI
from src.db.query import fetch_question_data

# Default run IDs from CLAUDE.md evaluation matrix
DYNAMIC_RUN_ID = "4ab1263aff1c43a589a7e15bb2d67b48"  # dynamic-None-doc
STATIC_RUN_ID = "d252e3844235428aa52ced2470b9b846"  # static-None

OUTPUT_DIR = Path("outputs/eval/execution_traces")

TRACE_FETCH_TIMEOUT = 15  # seconds per trace fetch


class TraceFetchTimeout(Exception):
    pass


def _timeout_handler(signum: int, frame: object) -> None:
    raise TraceFetchTimeout("Trace fetch timed out")


CATEGORY_NAMES = {
    1: "Direct Property",
    2: "Aggregation",
    3: "Computation",
    4: "Estimation/Unavailable",
}


def fetch_run_ids_with_traces(
    client: MlflowClient, experiment_id: str
) -> dict[str, str]:
    """Batch-fetch trace metadata (no spans) to build run_id -> trace_id mapping."""
    mapping: dict[str, str] = {}
    page_token = None

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        while True:
            kwargs: dict = {
                "experiment_ids": [experiment_id],
                "max_results": 100,
                "include_spans": False,
            }
            if page_token:
                kwargs["page_token"] = page_token
            traces = client.search_traces(**kwargs)

            for t in traces:
                rm = t.info.request_metadata or {}
                source_run = rm.get("mlflow.sourceRun")
                if source_run:
                    mapping[source_run] = t.info.trace_id

            if not traces.token:
                break
            page_token = traces.token

    return mapping


def load_run_classifications(
    client: MlflowClient, parent_run_id: str
) -> dict[int, dict]:
    """Load question_id -> run_data mapping for a parent run."""
    parent_run = client.get_run(parent_run_id)
    experiment_id = parent_run.info.experiment_id

    nested_runs = fetch_nested_runs(client, parent_run_id, experiment_id)
    result: dict[int, dict] = {}
    for nested_run in nested_runs:
        run_data = extract_run_data(nested_run)
        qid = run_data.get("question_id")
        if qid is not None:
            run_data["nested_run_id"] = nested_run.info.run_id
            run_data["experiment_id"] = experiment_id
            result[int(qid)] = run_data
    return result


def find_candidates(
    dynamic_data: dict[int, dict],
    static_data: dict[int, dict],
    question_metadata: dict[int, dict],
    run_trace_mapping: dict[str, str],
) -> list[dict]:
    """Find multi-iteration correct traces, preferring those where static fails.

    Primary criteria: dynamic=correct, iterations>2, trace available.
    Bonus: static=wrong/abstained (for stronger examples).
    """
    candidates = []
    for qid, dyn in dynamic_data.items():
        if dyn["classification"] != "correct":
            continue
        if dyn["num_iterations"] <= 2:
            continue

        trace_id = run_trace_mapping.get(dyn["nested_run_id"])
        stat = static_data.get(qid)
        stat_class = stat["classification"] if stat else "not_evaluated"
        static_fails = stat_class in ("wrong", "abstained")

        q_meta = question_metadata.get(qid, {})
        candidates.append({
            "question_id": qid,
            "question": q_meta.get("question", ""),
            "ground_truth": q_meta.get("ground_truth", ""),
            "category": q_meta.get("category"),
            "category_name": CATEGORY_NAMES.get(q_meta.get("category", 0), "Unknown"),
            "project_name": q_meta.get("project_name", ""),
            "model_name": q_meta.get("model_name", ""),
            "dynamic_classification": dyn["classification"],
            "static_classification": stat_class,
            "static_fails": static_fails,
            "num_iterations": dyn["num_iterations"],
            "cobbie_answer": dyn["cobbie_answer"],
            "dynamic_nested_run_id": dyn["nested_run_id"],
            "dynamic_experiment_id": dyn["experiment_id"],
            "trace_id": trace_id,
            "has_trace": trace_id is not None,
        })

    # Sort: trace available first, then static-fails first, then by iterations desc
    candidates.sort(
        key=lambda c: (not c["has_trace"], not c["static_fails"], -c["num_iterations"])
    )
    return candidates


def extract_iterations_from_trace(trace: Trace) -> list[dict]:
    """Extract iteration data from a trace object."""
    spans = trace.data.spans if trace.data else []
    if not spans:
        return []

    # Build parent_id -> children mapping
    children: dict[str, list] = {}
    for span in spans:
        parent = getattr(span, "parent_id", None)
        if parent:
            children.setdefault(parent, []).append(span)

    iterations: list[dict] = []
    for span in sorted(spans, key=lambda s: s.start_time_ns or 0):
        if not span.name.startswith("Iteration_"):
            continue

        iteration_data: dict = {
            "iteration": span.name,
            "status": str(span.status) if span.status else "unknown",
            "duration_s": round(
                ((span.end_time_ns or 0) - (span.start_time_ns or 0)) / 1e9, 2
            ),
        }

        child_spans = children.get(span.span_id, [])
        for child in sorted(child_spans, key=lambda s: s.start_time_ns or 0):
            if child.name.startswith("LLM_call_"):
                outputs = child.outputs or {}
                iteration_data["result_type"] = outputs.get("result_type", "")
                iteration_data["thoughts"] = outputs.get("thoughts", "")
                iteration_data["python_code"] = outputs.get("python_code", "")
                if "answer" in outputs:
                    iteration_data["answer"] = outputs["answer"]
                attrs = child.attributes or {}
                iteration_data["input_tokens"] = attrs.get("input_tokens", 0)
                iteration_data["output_tokens"] = attrs.get("output_tokens", 0)
            elif child.name.startswith("code_action_"):
                outputs = child.outputs or {}
                iteration_data["code_output"] = outputs.get(
                    "result_code_evaluation", ""
                )

        iterations.append(iteration_data)

    return iterations


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract execution traces for qualitative analysis"
    )
    parser.add_argument(
        "--dynamic-run",
        default=DYNAMIC_RUN_ID,
        help="Parent run ID for dynamic system",
    )
    parser.add_argument(
        "--static-run",
        default=STATIC_RUN_ID,
        help="Parent run ID for static baseline",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=10,
        help="Maximum number of candidate traces to extract",
    )
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    mlflow.set_tracking_uri(MLFLOW_URI)
    client = MlflowClient(tracking_uri=MLFLOW_URI)

    # Step 1: Scan trace metadata (fast, no spans)
    parent_run = client.get_run(args.dynamic_run)
    experiment_id = parent_run.info.experiment_id

    print("Scanning trace metadata...")
    run_trace_mapping = fetch_run_ids_with_traces(client, experiment_id)
    print(f"  Found {len(run_trace_mapping)} runs with traces")

    # Step 2: Load classifications
    print("Loading dynamic run data...")
    dynamic_data = load_run_classifications(client, args.dynamic_run)
    print(f"  Found {len(dynamic_data)} questions")

    print("Loading static run data...")
    static_data = load_run_classifications(client, args.static_run)
    print(f"  Found {len(static_data)} questions")

    # Step 3: Get question metadata
    all_qids = list(set(dynamic_data.keys()) | set(static_data.keys()))
    question_metadata = fetch_question_data(all_qids)

    # Step 4: Find candidates
    candidates = find_candidates(
        dynamic_data, static_data, question_metadata, run_trace_mapping
    )

    with_traces = sum(1 for c in candidates if c["has_trace"])
    without_traces = len(candidates) - with_traces
    print(
        f"\nFound {len(candidates)} candidates "
        f"({with_traces} with traces, {without_traces} without)"
    )

    if not candidates:
        print("No candidates found.")
        return

    cat_counts: dict[str, int] = {}
    for c in candidates:
        if c["has_trace"]:
            name = c["category_name"]
            cat_counts[name] = cat_counts.get(name, 0) + 1
    print(f"Category distribution (with traces): {cat_counts}")

    # Step 5: Fetch traces, skipping corrupted ones until we have enough
    traceable = [c for c in candidates if c["has_trace"]]
    print(f"\nExtracting traces (target: {args.max_candidates}, pool: {len(traceable)})...\n")

    extracted = 0
    for candidate in traceable:
        if extracted >= args.max_candidates:
            break

        qid = candidate["question_id"]
        trace_id = candidate["trace_id"]

        print(
            f"  Q{qid} ({candidate['category_name']}, "
            f"{candidate['num_iterations']} iters, "
            f"project={candidate['project_name']}) ... ",
            end="",
            flush=True,
        )

        try:
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(TRACE_FETCH_TIMEOUT)
            trace = client.get_trace(trace_id)
            iterations = extract_iterations_from_trace(trace)
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
        except (TraceFetchTimeout, Exception):
            signal.alarm(0)
            print("corrupted/slow trace, skipping")
            continue

        trace_output = {
            "question_id": qid,
            "question": candidate["question"],
            "ground_truth": candidate["ground_truth"],
            "category": candidate["category"],
            "category_name": candidate["category_name"],
            "project_name": candidate["project_name"],
            "model_name": candidate["model_name"],
            "dynamic_classification": candidate["dynamic_classification"],
            "static_classification": candidate["static_classification"],
            "num_iterations": candidate["num_iterations"],
            "cobbie_answer": candidate["cobbie_answer"],
            "iterations": iterations,
        }

        trace_path = OUTPUT_DIR / f"trace_q{qid}.json"
        with open(trace_path, "w") as f:
            json.dump(trace_output, f, indent=2, default=str)
        extracted += 1
        print(f"{len(iterations)} iterations [{extracted}/{args.max_candidates}]")

    print(f"\nExtracted {extracted} traces")

    # Step 6: Write summary CSV
    summary_path = OUTPUT_DIR / "candidates_summary.csv"
    with open(summary_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "question_id",
            "project_name",
            "category",
            "category_name",
            "num_iterations",
            "dynamic_classification",
            "static_classification",
            "has_trace",
            "question_preview",
        ])
        for c in candidates:
            writer.writerow([
                c["question_id"],
                c["project_name"],
                c["category"],
                c["category_name"],
                c["num_iterations"],
                c["dynamic_classification"],
                c["static_classification"],
                c["has_trace"],
                c["question"][:100],
            ])

    print(f"\nWrote summary to {summary_path}")
    print(f"Trace JSONs in {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
