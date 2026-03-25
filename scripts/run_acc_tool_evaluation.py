"""Run all ACC tools against test models and produce a detailed error analysis.

Executes each tool from acc/tools/ against the 4 test models, compares
predicted GUIDs with ground truth, and generates:
  - outputs/acc/tool_evaluation_results.json  (machine-readable)
  - outputs/acc/tool_evaluation_report.md     (human-readable error analysis)

Usage:
    uv run scripts/run_acc_tool_evaluation.py
"""

import json
import multiprocessing
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.acc.guid_comparison import (  # noqa: E402
    compare_guids,
    get_expected_guids,
    get_rule_context,
    load_model_splits,
)
from src.config import ACC_MODELS_PATH, ACC_TOOLS_PATH, get_boilerplate  # noqa: E402
from src.tools.initial.classify_spaces import classify_spaces  # noqa: E402
from src.tools.initial.query_ifcopenshell_documentation import query_ifcopenshell_docs  # noqa: E402

ACC_EXECUTION_TOOLS = {
    "query_ifcopenshell_docs": query_ifcopenshell_docs,
    "classify_spaces": classify_spaces,
}

OUTPUT_DIR = PROJECT_ROOT / "outputs" / "acc"


# ---------------------------------------------------------------------------
# Tool execution (subprocess-isolated, reuses the pattern from training)
# ---------------------------------------------------------------------------


def _execute_tool_worker(
    queue: multiprocessing.Queue,
    tool_code: str,
    function_name: str,
    model_path: str,
    boilerplate: str,
) -> None:
    from src.util.python_executor import setup_interpreter, execute_python

    try:
        interpreter = setup_interpreter(
            model_path=model_path,
            tools=ACC_EXECUTION_TOOLS,
            boilerplate=boilerplate,
        )
        load_log = execute_python(
            tool_code, tools=ACC_EXECUTION_TOOLS, interpreter=interpreter
        )
        call_code = f"_result = {function_name}(path_ifc_model)"
        call_log = execute_python(
            call_code, tools=ACC_EXECUTION_TOOLS, interpreter=interpreter
        )
        log = load_log + "\n" + call_log

        result = interpreter.locals.get("_result")
        if isinstance(result, list):
            guids = [str(g) for g in result]
        else:
            guids = []
        queue.put(("ok", guids, log))
    except Exception as e:
        queue.put(("error", [], str(e)))


def execute_tool_safe(
    tool_code: str,
    function_name: str,
    model_path: str,
    boilerplate: str,
    timeout: int = 300,
    max_retries: int = 2,
) -> tuple[list[str], str]:
    mp_ctx = multiprocessing.get_context("spawn")

    for attempt in range(max_retries + 1):
        queue = mp_ctx.Queue()
        proc = mp_ctx.Process(
            target=_execute_tool_worker,
            args=(queue, tool_code, function_name, model_path, boilerplate),
        )
        proc.start()
        proc.join(timeout=timeout)

        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=5)
            return [], f"Timeout after {timeout}s"

        exit_code = proc.exitcode
        if exit_code == 0:
            status, guids, log = queue.get_nowait()
            if status == "ok":
                return guids, log
            return [], f"Error: {log}"
        elif exit_code is not None and exit_code < 0:
            signal_num = -exit_code
            if signal_num == 11 and attempt < max_retries:
                print(
                    f"    Segfault attempt {attempt + 1}/{max_retries + 1}, retrying..."
                )
                continue
            return [], f"Signal {signal_num} after {attempt + 1} attempts"
        else:
            return [], f"Exit code {exit_code}"

    return [], "Unexpected loop exit"


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_tools() -> list[dict]:
    """Find all check_*.py tool files and extract function names."""
    tools_dir = Path(ACC_TOOLS_PATH)
    tools = []
    for py_file in sorted(tools_dir.glob("check_*.py")):
        func_name = py_file.stem  # e.g. check_slab_thickness
        rule_title = func_name.replace("check_", "")  # e.g. slab_thickness
        code = py_file.read_text(encoding="utf-8")
        tools.append(
            {
                "file": str(py_file),
                "function_name": func_name,
                "rule_title": rule_title,
                "code": code,
            }
        )
    return tools


def get_test_models() -> list[dict]:
    """Return test model names and IFC paths."""
    splits = load_model_splits()
    models = []
    for name in splits["test"]:
        ifc_path = Path(ACC_MODELS_PATH) / name / "arc.ifc"
        if ifc_path.exists():
            models.append({"name": name, "path": str(ifc_path)})
        else:
            print(f"WARNING: IFC not found for test model '{name}': {ifc_path}")
    return models


# ---------------------------------------------------------------------------
# Main evaluation
# ---------------------------------------------------------------------------


def _build_guid_type_map(ifc_path: str) -> dict[str, str]:
    """Open an IFC file and return a mapping of GlobalId -> IFC entity type."""
    import ifcopenshell

    ifc_model = ifcopenshell.open(ifc_path)
    guid_map: dict[str, str] = {}
    for entity in ifc_model:
        gid = getattr(entity, "GlobalId", None)
        if gid:
            guid_map[gid] = entity.is_a()
    return guid_map


def _annotate_guids(
    guids: list[str], guid_type_map: dict[str, str]
) -> list[dict[str, str]]:
    """Convert a list of GUID strings to [{"guid": ..., "type": ...}, ...]."""
    return [{"guid": g, "type": guid_type_map.get(g, "Unknown")} for g in guids]


def run_evaluation() -> dict:
    tools = discover_tools()
    models = get_test_models()
    boilerplate = get_boilerplate()

    print(
        f"Running {len(tools)} tools x {len(models)} test models = {len(tools) * len(models)} executions\n"
    )

    # Pre-load GUID -> IFC type maps for each model
    print("Loading IFC type maps...")
    guid_type_maps: dict[str, dict[str, str]] = {}
    for model in models:
        print(f"  [{model['name']}] ", end="", flush=True)
        guid_type_maps[model["name"]] = _build_guid_type_map(model["path"])
        print(f"{len(guid_type_maps[model['name']])} entities")
    print()

    results: dict = {
        "metadata": {
            "timestamp": datetime.now().isoformat(),
            "num_tools": len(tools),
            "num_models": len(models),
            "models": [m["name"] for m in models],
        },
        "rules": {},
    }

    global_tp, global_fp, global_fn = 0, 0, 0

    for tool in tools:
        rule_title = tool["rule_title"]
        func_name = tool["function_name"]
        print(f"=== {rule_title} ===")

        rule_result: dict = {"models": {}, "aggregated": {}}
        rule_tp, rule_fp, rule_fn = 0, 0, 0

        for model in models:
            model_name = model["name"]
            guid_map = guid_type_maps[model_name]
            print(f"  [{model_name}] ", end="", flush=True)
            t0 = time.time()

            # Execute tool
            predicted, log = execute_tool_safe(
                tool["code"], func_name, model["path"], boilerplate
            )
            elapsed = time.time() - t0

            # Get expected GUIDs
            try:
                expected = get_expected_guids(model_name, rule_title)
            except (FileNotFoundError, KeyError) as e:
                print(f"ground truth error: {e}")
                rule_result["models"][model_name] = {"error": str(e)}
                continue

            # Compare
            cmp = compare_guids(set(predicted), set(expected))

            # Identify specific TP/FP/FN GUIDs
            predicted_set = set(predicted)
            expected_set = set(expected)
            tp_guids = sorted(predicted_set & expected_set)
            fp_guids = sorted(predicted_set - expected_set)
            fn_guids = sorted(expected_set - predicted_set)

            rule_tp += cmp.tp
            rule_fp += cmp.fp
            rule_fn += cmp.fn

            # Get issue context for FN GUIDs (what we missed)
            fn_context = []
            try:
                ctx = get_rule_context(model_name, rule_title)
                for issue in ctx.get("issues", []):
                    missed = [
                        g
                        for g in issue.get("required_guids", [])
                        if g in expected_set - predicted_set
                    ]
                    if missed:
                        fn_context.append(
                            {
                                "title": issue.get("title", ""),
                                "description": issue.get("description", ""),
                                "missed_guids": _annotate_guids(missed, guid_map),
                                "all_guids": _annotate_guids(
                                    issue.get("all_guids", []), guid_map
                                ),
                            }
                        )
            except (FileNotFoundError, KeyError):
                pass

            status = "PASS" if cmp.is_perfect_match else f"F1={cmp.f1:.2f}"
            print(f"{status} (TP={cmp.tp} FP={cmp.fp} FN={cmp.fn}) [{elapsed:.1f}s]")

            rule_result["models"][model_name] = {
                "predicted": _annotate_guids(sorted(predicted), guid_map),
                "expected": _annotate_guids(sorted(expected), guid_map),
                "tp_guids": _annotate_guids(tp_guids, guid_map),
                "fp_guids": _annotate_guids(fp_guids, guid_map),
                "fn_guids": _annotate_guids(fn_guids, guid_map),
                "tp": cmp.tp,
                "fp": cmp.fp,
                "fn": cmp.fn,
                "precision": cmp.precision,
                "recall": cmp.recall,
                "f1": cmp.f1,
                "is_perfect_match": cmp.is_perfect_match,
                "elapsed_seconds": round(elapsed, 1),
                "fn_context": fn_context,
                "log": log[:500] if log else "",
            }

        # Aggregated rule metrics
        agg_p = (
            rule_tp / (rule_tp + rule_fp)
            if (rule_tp + rule_fp) > 0
            else (1.0 if rule_fn == 0 else 0.0)
        )
        agg_r = (
            rule_tp / (rule_tp + rule_fn)
            if (rule_tp + rule_fn) > 0
            else (1.0 if rule_fp == 0 else 0.0)
        )
        agg_f1 = 2 * agg_p * agg_r / (agg_p + agg_r) if (agg_p + agg_r) > 0 else 0.0
        if rule_tp == 0 and rule_fp == 0 and rule_fn == 0:
            agg_f1 = 1.0

        rule_result["aggregated"] = {
            "tp": rule_tp,
            "fp": rule_fp,
            "fn": rule_fn,
            "precision": round(agg_p, 4),
            "recall": round(agg_r, 4),
            "f1": round(agg_f1, 4),
        }
        results["rules"][rule_title] = rule_result

        global_tp += rule_tp
        global_fp += rule_fp
        global_fn += rule_fn
        print(
            f"  Aggregated: F1={agg_f1:.3f} (TP={rule_tp} FP={rule_fp} FN={rule_fn})\n"
        )

    # Global metrics
    g_p = global_tp / (global_tp + global_fp) if (global_tp + global_fp) > 0 else 0.0
    g_r = global_tp / (global_tp + global_fn) if (global_tp + global_fn) > 0 else 0.0
    g_f1 = 2 * g_p * g_r / (g_p + g_r) if (g_p + g_r) > 0 else 0.0

    results["global"] = {
        "tp": global_tp,
        "fp": global_fp,
        "fn": global_fn,
        "precision": round(g_p, 4),
        "recall": round(g_r, 4),
        "f1": round(g_f1, 4),
    }

    return results


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report(results: dict) -> str:
    lines = [
        "# ACC Tool Evaluation Report — Test Models",
        f"\nGenerated: {results['metadata']['timestamp']}",
        f"Models: {', '.join(results['metadata']['models'])}",
        "",
    ]

    # Global summary
    g = results["global"]
    lines.append("## Global Summary")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| F1 (aggregated) | **{g['f1']:.3f}** |")
    lines.append(f"| Precision | {g['precision']:.3f} |")
    lines.append(f"| Recall | {g['recall']:.3f} |")
    lines.append(f"| TP / FP / FN | {g['tp']} / {g['fp']} / {g['fn']} |")
    lines.append("")

    # Per-rule summary table
    lines.append("## Per-Rule Summary")
    lines.append("| Rule | F1 | Precision | Recall | TP | FP | FN |")
    lines.append("|------|---:|----------:|-------:|---:|---:|---:|")
    for rule_title, rule_data in results["rules"].items():
        a = rule_data["aggregated"]
        lines.append(
            f"| {rule_title} | {a['f1']:.3f} | {a['precision']:.3f} | {a['recall']:.3f} "
            f"| {a['tp']} | {a['fp']} | {a['fn']} |"
        )
    lines.append("")

    # Detailed error analysis per rule
    lines.append("## Detailed Error Analysis")
    lines.append("")

    for rule_title, rule_data in results["rules"].items():
        a = rule_data["aggregated"]
        has_errors = a["fp"] > 0 or a["fn"] > 0
        if not has_errors:
            lines.append(f"### {rule_title} — F1={a['f1']:.3f} (PERFECT)")
            lines.append("No errors on test models.\n")
            continue

        lines.append(f"### {rule_title} — F1={a['f1']:.3f}")
        lines.append("")

        for model_name, m in rule_data["models"].items():
            if "error" in m:
                lines.append(f"**{model_name}**: Ground truth error — {m['error']}")
                continue

            if m["is_perfect_match"]:
                lines.append(f"**{model_name}**: PASS (TP={m['tp']})")
                continue

            lines.append(
                f"**{model_name}**: F1={m['f1']:.2f} | P={m['precision']:.2f} R={m['recall']:.2f} | TP={m['tp']} FP={m['fp']} FN={m['fn']}"
            )

            if m["fp_guids"]:
                lines.append(
                    f"  - **False Positives** (predicted but not expected): {len(m['fp_guids'])} GUIDs"
                )
                for guid in m["fp_guids"]:
                    lines.append(f"    - `{guid}`")

            if m["fn_guids"]:
                lines.append(
                    f"  - **False Negatives** (expected but missed): {len(m['fn_guids'])} GUIDs"
                )
                for ctx in m.get("fn_context", []):
                    lines.append(
                        f"    - **{ctx['title']}**: {ctx['description'].strip()[:200]}"
                    )
                    for guid in ctx["missed_guids"]:
                        lines.append(f"      - `{guid}`")

            lines.append("")

        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    results = run_evaluation()

    # Save JSON
    json_path = OUTPUT_DIR / "tool_evaluation_results.json"
    json_path.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\nJSON results: {json_path}")

    # Save markdown report
    report = generate_report(results)
    md_path = OUTPUT_DIR / "tool_evaluation_report.md"
    md_path.write_text(report, encoding="utf-8")
    print(f"Report: {md_path}")

    # Print global summary
    g = results["global"]
    print(f"\nGlobal test F1={g['f1']:.3f} (TP={g['tp']} FP={g['fp']} FN={g['fn']})")
