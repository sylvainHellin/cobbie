"""Exploratory cost / size / accuracy figure for the 3 models (R2 C4-C5 support).

Relates per-model AGENTIC accuracy (pooled none+tools) to:
  - cost  (USD per question, cache-aware mean), and
  - model size (parameters; MoE total, with active annotated),

so the author can eyeball whether higher cost / larger size buys higher accuracy.

Panel (a) encodes total parameters as marker area; panel (b) encodes cost/q as
marker area (so size vs accuracy carries the cost dimension as bubble size).

Honesty caveat: n=3 models. This is illustrative only. No correlation
coefficient is computed or implied; three points cannot establish a trend.

Data sources (read-only):
  - accuracy: outputs/factorial/<cell>/results.sqlite, classification='correct'
              pooled over the two agentic cells (none + tools) per model.
  - cost:     same DBs, cache-aware USD/q using the documented list rates below
              (replicates scripts/efficiency_boxplots.py). cached_input_tokens
              billed at the cache-hit rate, the rest at the cache-miss rate.
  - params:   web-sourced published counts (see PARAMS, with sources).

Never touches outputs/factorial_rerun_20260624.

Reproduce with:

    uv run --with matplotlib --with pandas --with numpy python scripts/cost_size_accuracy.py
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
FACTORIAL = REPO / "outputs" / "factorial"
FIG_DIR = REPO / "outputs" / "analysis" / "figures"

MODELS = ["glm-4.5-air", "glm-5.2", "minimax-m3"]
AUGS = ["none", "tools"]

# Documented list pricing (USD per 1M tokens): in_miss / cached / output.
# Same rates as scripts/efficiency_boxplots.py.
#   glm-5.2, glm-4.5-air : official docs.z.ai list rates.
#   minimax-m3           : platform.minimax.io list rate (a 50% launch promo
#                          would halve it). Cache storage is not modeled.
PRICING = {
    "glm-5.2": (1.40, 0.26, 4.40),
    "minimax-m3": (0.60, 0.12, 2.40),
    "glm-4.5-air": (0.20, 0.03, 1.10),
}

# Published parameter counts (MoE). total_B / active_B in billions.
# All three were credibly sourced; none left unknown.
#   glm-4.5-air : 106B total / 12B active.
#                 Z.ai docs (docs.z.ai/guides/llm/glm-4.5), HF zai-org/GLM-4.5-Air,
#                 GLM-4.5 tech report arXiv:2508.06471.
#   glm-5.2     : 744B total / ~40B active.
#                 HF zai-org/GLM-5.2, zai-org/GLM-5 README.
#   minimax-m3  : ~428B total / ~23B active.
#                 HF MiniMaxAI/MiniMax-M3, MiniMax M3 blog (minimax.io/blog/minimax-m3).
PARAMS = {
    "glm-4.5-air": {"total_B": 106.0, "active_B": 12.0},
    "glm-5.2": {"total_B": 744.0, "active_B": 40.0},
    "minimax-m3": {"total_B": 428.0, "active_B": 23.0},
}

# Axis convention: size axis uses TOTAL parameters; active is annotated only.

LABEL_OFFSETS = {  # (dx, dy) in points, per panel, to avoid label overlap
    "cost": {"glm-4.5-air": (8, -2), "glm-5.2": (8, 4), "minimax-m3": (8, -10)},
    "size": {"glm-4.5-air": (10, -2), "glm-5.2": (-10, 8), "minimax-m3": (8, -12)},
}


def load_model_stats() -> pd.DataFrame:
    rows = []
    for model in MODELS:
        in_miss, cached, out = PRICING[model]
        correct = total = 0
        costs = []
        for aug in AUGS:
            db = FACTORIAL / f"{model}__agentic__{aug}" / "results.sqlite"
            if not db.exists():
                raise FileNotFoundError(f"missing cell db: {db}")
            uri = f"file:{db}?mode=ro"
            with sqlite3.connect(uri, uri=True) as con:
                df = pd.read_sql_query(
                    "SELECT classification, input_tokens, cached_input_tokens, "
                    "output_tokens FROM results",
                    con,
                )
            total += len(df)
            correct += int((df["classification"] == "correct").sum())
            inp = df["input_tokens"].fillna(0).to_numpy(float)
            cin = df["cached_input_tokens"].fillna(0).to_numpy(float)
            outp = df["output_tokens"].fillna(0).to_numpy(float)
            c = ((inp - cin) * in_miss + cin * cached + outp * out) / 1e6
            costs.extend(c.tolist())
        costs = np.asarray(costs, float)
        rows.append(
            {
                "model": model,
                "n_questions": total,
                "correct": correct,
                "accuracy": correct / total,
                "cost_mean": float(np.mean(costs)),
                "cost_median": float(np.median(costs)),
                "total_B": PARAMS[model]["total_B"],
                "active_B": PARAMS[model]["active_B"],
            }
        )
    return pd.DataFrame(rows).set_index("model").loc[MODELS]


COLORS = {
    "glm-4.5-air": "#4C72B0",
    "glm-5.2": "#C44E52",
    "minimax-m3": "#55A868",
}


def make_figure(stats: pd.DataFrame) -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "figure.dpi": 150,
            "savefig.bbox": "tight",
        }
    )
    fig, (axc, axs) = plt.subplots(1, 2, figsize=(9.6, 4.2))

    # Marker size proportional to total params (encodes the 3rd dimension).
    smin, smax = 120.0, 900.0
    pmin, pmax = stats["total_B"].min(), stats["total_B"].max()
    sizes = smin + (stats["total_B"] - pmin) / (pmax - pmin) * (smax - smin)

    # Panel A: cost vs accuracy, marker size ~ total params.
    for model, r in stats.iterrows():
        axc.scatter(
            r["cost_mean"], r["accuracy"], s=sizes[model], color=COLORS[model],
            alpha=0.85, edgecolor="black", linewidth=0.7, zorder=3,
        )
        dx, dy = LABEL_OFFSETS["cost"][model]
        axc.annotate(
            f"{model}\n{r['accuracy']:.3f} acc, ${r['cost_mean']:.4f}/q",
            (r["cost_mean"], r["accuracy"]), textcoords="offset points",
            xytext=(dx, dy), fontsize=8.2, va="center",
        )
    axc.set_xlabel("Cost (USD per question, cache-aware mean)")
    axc.set_ylabel("Accuracy (agentic, pooled none+tools)")
    axc.set_title("(a) Cost vs accuracy\nmarker area $\\propto$ total parameters")
    axc.set_xlim(left=0)
    axc.grid(True, alpha=0.3)

    # Panel B: total params vs accuracy, marker area ~ cost/q (cache-aware mean).
    cmin, cmax = stats["cost_mean"].min(), stats["cost_mean"].max()

    def cost_to_size(c: float) -> float:
        return smin + (c - cmin) / (cmax - cmin) * (smax - smin)

    for model, r in stats.iterrows():
        axs.scatter(
            r["total_B"], r["accuracy"], s=cost_to_size(r["cost_mean"]),
            color=COLORS[model], alpha=0.85, edgecolor="black", linewidth=0.7,
            zorder=3,
        )
        dx, dy = LABEL_OFFSETS["size"][model]
        ha = "right" if dx < 0 else "left"
        axs.annotate(
            f"{model}\n{r['total_B']:.0f}B total / {r['active_B']:.0f}B active"
            f"\n${r['cost_mean']:.4f}/q",
            (r["total_B"], r["accuracy"]), textcoords="offset points",
            xytext=(dx, dy), fontsize=8.2, va="center", ha=ha,
        )
    axs.set_xlabel("Model size (total parameters, billions; MoE)")
    axs.set_ylabel("Accuracy (agentic, pooled none+tools)")
    axs.set_title("(b) Size vs accuracy\nmarker area $\\propto$ cost per question")
    axs.set_xlim(0, stats["total_B"].max() * 1.18)
    axs.grid(True, alpha=0.3)

    # Size legend for panel B: representative cost/q levels spanning the range.
    legend_costs = [0.01, 0.04, 0.066]
    size_handles = [
        axs.scatter(
            [], [], s=cost_to_size(c), color="0.6", alpha=0.7,
            edgecolor="black", linewidth=0.7, label=f"${c:.3f}/q",
        )
        for c in legend_costs
    ]
    axs.legend(
        handles=size_handles, title="bubble size = cost/q", loc="lower right",
        labelspacing=1.6, borderpad=1.0, handletextpad=1.4, scatterpoints=1,
        frameon=True, fontsize=8, title_fontsize=8,
    )

    # Shared y-limits for visual comparability.
    ymin = stats["accuracy"].min() - 0.06
    ymax = stats["accuracy"].max() + 0.06
    axc.set_ylim(ymin, ymax)
    axs.set_ylim(ymin, ymax)

    fig.suptitle(
        "Per-model cost / size / accuracy (agentic BIM IR) -- exploratory, n=3 models",
        fontsize=11, y=1.02,
    )
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(FIG_DIR / f"cost_size_accuracy_20260625.{ext}")
    plt.close(fig)


def main() -> None:
    stats = load_model_stats()
    pd.set_option("display.float_format", lambda v: f"{v:.4f}")
    print(stats.to_string())
    make_figure(stats)
    print(f"\nSaved: {FIG_DIR / 'cost_size_accuracy_20260625.{pdf,png}'}")


if __name__ == "__main__":
    main()
