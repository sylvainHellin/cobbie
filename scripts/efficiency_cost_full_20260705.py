"""Compute the full efficiency + cost table for the 12 factorial cells.

Read-only on outputs/factorial/<cell>/results.sqlite. Pure stdlib.
"""

from __future__ import annotations

import math
import sqlite3
import statistics
from pathlib import Path

REPO = Path.home() / "code" / "tum" / "cobbie"
FACTORIAL = REPO / "outputs" / "factorial"
OUT = REPO / "outputs" / "analysis" / "efficiency_cost_full_20260705.md"

MODELS = ["glm-4.5-air", "glm-5.2", "minimax-m3"]
PARADIGMS = ["agentic", "static"]
TOOLS = ["none", "tools"]

# Copied verbatim from scripts/cost_size_accuracy.py: (in_miss, cached, out) USD/1M.
PRICING = {
    "glm-5.2": (1.40, 0.26, 4.40),
    "minimax-m3": (0.60, 0.12, 2.40),
    "glm-4.5-air": (0.20, 0.03, 1.10),
}

# Known validation figures (pooled none+tools agentic) from cost_size_accuracy_20260625.md
KNOWN_POOLED_COST = {
    "glm-4.5-air": (0.0098, 0.0080),
    "minimax-m3": (0.0365, 0.0268),
    "glm-5.2": (0.0658, 0.0494),
}


def p95_nearest_rank(sorted_vals: list[float]) -> float:
    """Nearest-rank p95: value at 1-indexed rank ceil(0.95*n)."""
    n = len(sorted_vals)
    rank = math.ceil(0.95 * n)
    rank = max(1, min(rank, n))
    return sorted_vals[rank - 1]


def load_cell(model: str, paradigm: str, tools: str) -> dict:
    db = FACTORIAL / f"{model}__{paradigm}__{tools}" / "results.sqlite"
    if not db.exists():
        raise FileNotFoundError(db)
    uri = f"file:{db}?mode=ro"
    with sqlite3.connect(uri, uri=True) as con:
        rows = con.execute(
            "SELECT input_tokens, cached_input_tokens, output_tokens, "
            "latency_s, num_iterations FROM results"
        ).fetchall()
    iters, lats, toks, costs = [], [], [], []
    in_miss, cached, out = PRICING[model]
    for inp, cin, outp, lat, it in rows:
        inp = inp or 0
        cin = cin or 0
        outp = outp or 0
        lat = lat or 0.0
        it = it or 0
        iters.append(it)
        lats.append(lat)
        toks.append(inp + outp)
        costs.append(((inp - cin) * in_miss + cin * cached + outp * out) / 1e6)
    return {
        "n": len(rows),
        "iters": iters,
        "lats": lats,
        "toks": toks,
        "costs": costs,
    }


def summarize(cell: dict) -> dict:
    iters = sorted(cell["iters"])
    lats = cell["lats"]
    toks = cell["toks"]
    costs = cell["costs"]
    return {
        "n": cell["n"],
        "it_mean": statistics.mean(iters),
        "it_median": statistics.median(iters),
        "it_p95": p95_nearest_rank(iters),
        "it_max": max(iters),
        "lat_mean": statistics.mean(lats),
        "lat_median": statistics.median(lats),
        "tok_mean": statistics.mean(toks),
        "tok_median": statistics.median(toks),
        "cost_mean": statistics.mean(costs),
        "cost_median": statistics.median(costs),
    }


def merge(cells: list[dict]) -> dict:
    return {
        "n": sum(c["n"] for c in cells),
        "iters": [x for c in cells for x in c["iters"]],
        "lats": [x for c in cells for x in c["lats"]],
        "toks": [x for c in cells for x in c["toks"]],
        "costs": [x for c in cells for x in c["costs"]],
    }


def main() -> None:
    # Load all 12 cells, assert 514 rows each.
    cells: dict[tuple[str, str, str], dict] = {}
    problems = []
    for m in MODELS:
        for p in PARADIGMS:
            for t in TOOLS:
                c = load_cell(m, p, t)
                cells[(m, p, t)] = c
                if c["n"] != 514:
                    problems.append(f"{m}__{p}__{t}: n={c['n']} (expected 514)")
    if problems:
        print("ROW COUNT PROBLEMS:")
        for pr in problems:
            print("  " + pr)
    else:
        print("ROW COUNT OK: all 12 cells have exactly 514 rows.")

    # Per-cell summaries.
    per_cell = {k: summarize(v) for k, v in cells.items()}

    # Agentic rollups per model: none / tools / pooled.
    rollups: dict[tuple[str, str], dict] = {}
    for m in MODELS:
        none_c = cells[(m, "agentic", "none")]
        tools_c = cells[(m, "agentic", "tools")]
        pooled_c = merge([none_c, tools_c])
        rollups[(m, "none")] = summarize(none_c)
        rollups[(m, "tools")] = summarize(tools_c)
        rollups[(m, "pooled")] = summarize(pooled_c)

    # Validation of pooled cost vs known figures (4 decimals).
    print("\nPOOLED COST VALIDATION (4 decimals):")
    all_pass = True
    val_lines = []
    for m in MODELS:
        r = rollups[(m, "pooled")]
        km, kmed = KNOWN_POOLED_COST[m]
        got_m = round(r["cost_mean"], 4)
        got_med = round(r["cost_median"], 4)
        ok = (got_m == round(km, 4)) and (got_med == round(kmed, 4))
        all_pass = all_pass and ok
        status = "PASS" if ok else "FAIL"
        line = (f"  {m}: mean {got_m:.4f} (known {km:.4f}), "
                f"median {got_med:.4f} (known {kmed:.4f}) -> {status}")
        print(line)
        val_lines.append((m, got_m, km, got_med, kmed, ok))
    print(f"\nOVERALL VALIDATION: {'PASS' if all_pass else 'FAIL'}")

    # Write markdown.
    write_md(per_cell, rollups, val_lines, all_pass, bool(problems), problems)

    # Print agentic/none per-model rows for inline return.
    print("\nAGENTIC/NONE PER-MODEL ROWS:")
    for m in MODELS:
        r = rollups[(m, "none")]
        print(f"  {m}: it {r['it_mean']:.1f}/{r['it_median']:.0f}/{r['it_p95']:.0f}"
              f" | lat {r['lat_mean']:.1f}/{r['lat_median']:.1f}"
              f" | tok {r['tok_mean']:,.0f}/{r['tok_median']:,.0f}"
              f" | cost {r['cost_mean']:.4f}/{r['cost_median']:.4f}")


def write_md(per_cell, rollups, val_lines, all_pass, has_problems, problems) -> None:
    L = []
    L.append("# Full efficiency + cost table (AUTCON revision factorial, 12 cells)")
    L.append("")
    L.append("Date: 2026-07-05. Generated by `scripts/efficiency_cost_full_20260705.py` "
             "(read-only, `mode=ro`).")
    L.append("")
    L.append("## Source and method")
    L.append("")
    L.append("- Source dir: `outputs/factorial/<cell>/results.sqlite`, table `results`, "
             "one row per question (514 per cell, `repeat_idx=0`).")
    L.append("- Cells: model {glm-4.5-air, glm-5.2, minimax-m3} x paradigm "
             "{agentic, static} x tools {none, tools}, dir `<model>__<paradigm>__<tools>`.")
    L.append("- NULL token/latency/iteration fields treated as 0.")
    L.append("- `total_tokens = input_tokens + output_tokens` per question.")
    L.append("- Cost (USD/q), cache-aware, per row (formula + rates copied verbatim "
             "from `scripts/cost_size_accuracy.py`):")
    L.append("")
    L.append("  `cost = ((input_tokens - cached_input_tokens)*in_miss "
             "+ cached_input_tokens*cached + output_tokens*out) / 1e6`")
    L.append("")
    L.append("  Pricing (USD per 1M tokens; in_miss / cached / out):")
    L.append("")
    L.append("  | model | in_miss | cached | out |")
    L.append("  |---|---:|---:|---:|")
    for m in MODELS:
        a, b, c = PRICING[m]
        L.append(f"  | {m} | {a:.2f} | {b:.2f} | {c:.2f} |")
    L.append("")
    L.append("- p95 method: nearest-rank. For a sorted ascending list of length n, "
             "p95 = value at 1-indexed rank `ceil(0.95*n)` (for n=514, rank 489). "
             "No interpolation.")
    L.append("- mean/median via Python `statistics` (median averages the two central "
             "values for even n, matching numpy's default).")
    L.append("")
    L.append("Note: static cells have `num_iterations=1` by construction and exhibit "
             "heavy abstention, so their iteration/latency/token/cost figures are "
             "context only, not comparable to the agentic paradigm.")
    L.append("")

    # Validation block.
    L.append("## Pooled-cost validation")
    L.append("")
    L.append("Pooled (none+tools, n=1028) agentic cost mean/median vs the known figures "
             "in `cost_size_accuracy_20260625.md`, compared to 4 decimals.")
    L.append("")
    L.append("| model | cost mean (computed) | cost mean (known) | cost median (computed) "
             "| cost median (known) | match |")
    L.append("|---|---:|---:|---:|---:|:--:|")
    for m, got_m, km, got_med, kmed, ok in val_lines:
        L.append(f"| {m} | {got_m:.4f} | {km:.4f} | {got_med:.4f} | {kmed:.4f} | "
                 f"{'PASS' if ok else 'FAIL'} |")
    L.append("")
    L.append(f"Overall: **{'PASS' if all_pass else 'FAIL'}** "
             f"(all six figures match to 4 decimals)." if all_pass else
             f"Overall: **FAIL** (see discrepancies above).")
    L.append("")
    if has_problems:
        L.append("Row-count problems detected:")
        for pr in problems:
            L.append(f"- {pr}")
        L.append("")
    else:
        L.append("Row count: all 12 cells have exactly 514 rows (asserted).")
        L.append("")

    # Full 12-cell per-cell table.
    L.append("## Per-cell table (all 12 cells)")
    L.append("")
    L.append("| model | paradigm | tools | n | it mean | it median | it p95 | it max "
             "| lat mean (s) | lat median (s) | tok mean | tok median "
             "| cost mean (USD/q) | cost median (USD/q) |")
    L.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for m in MODELS:
        for p in PARADIGMS:
            for t in TOOLS:
                r = per_cell[(m, p, t)]
                L.append(
                    f"| {m} | {p} | {t} | {r['n']} | {r['it_mean']:.2f} | "
                    f"{r['it_median']:.1f} | {r['it_p95']:.0f} | {r['it_max']:.0f} | "
                    f"{r['lat_mean']:.2f} | {r['lat_median']:.2f} | "
                    f"{r['tok_mean']:,.0f} | {r['tok_median']:,.0f} | "
                    f"{r['cost_mean']:.4f} | {r['cost_median']:.4f} |"
                )
    L.append("")

    # Agentic per-model rollup tables.
    L.append("## Agentic per-model rollups (none / tools / pooled)")
    L.append("")
    L.append("Modes: none-only (n=514), tools-only (n=514), pooled none+tools (n=1028). "
             "Agentic cells only.")
    L.append("")

    def rollup_table(metric_cols: list[tuple[str, str, str]], title: str) -> None:
        L.append(f"### {title}")
        L.append("")
        header = "| model | mode | n | " + " | ".join(c[0] for c in metric_cols) + " |"
        sep = "|---|---|---:|" + "".join("---:|" for _ in metric_cols)
        L.append(header)
        L.append(sep)
        for m in MODELS:
            for mode in ("none", "tools", "pooled"):
                r = rollups[(m, mode)]
                vals = []
                for _, key, fmt in metric_cols:
                    vals.append(format(r[key], fmt))
                L.append(f"| {m} | {mode} | {r['n']} | " + " | ".join(vals) + " |")
        L.append("")

    rollup_table(
        [("mean", "it_mean", ".2f"), ("median", "it_median", ".1f"),
         ("p95", "it_p95", ".0f")],
        "Iterations",
    )
    rollup_table(
        [("mean (s)", "lat_mean", ".2f"), ("median (s)", "lat_median", ".2f")],
        "Latency (s)",
    )
    rollup_table(
        [("mean", "tok_mean", ",.0f"), ("median", "tok_median", ",.0f")],
        "Total tokens",
    )
    rollup_table(
        [("mean (USD/q)", "cost_mean", ".4f"), ("median (USD/q)", "cost_median", ".4f")],
        "Cost (cache-aware, USD/q)",
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L) + "\n")
    print(f"\nWrote: {OUT}")


if __name__ == "__main__":
    main()
