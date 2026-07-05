"""Efficiency box plots + summary stats for the 3x2x2 factorial (R2 C4/C5).

Reads the canonical judged factorial cells under outputs/factorial/<cell>/results.sqlite
and produces, for the three IR efficiency metrics, per-model box plots and a stats
summary markdown:

  - iterations   : results.num_iterations  (agentic search steps)
  - latency      : results.latency_s       (wall-clock seconds per question)
  - total_tokens : input_tokens + output_tokens  (pricing-free cost proxy; "COST/tokens")

Cell selection for the figures: AGENTIC cells only. The static cells are degenerate
on these metrics (one iteration by construction, heavy abstention), so an agentic-only
comparison is the honest efficiency story the reviewers asked about. Augmentation
(none/tools) is shown as a hue within each model. The markdown additionally reports the
full per-cell breakdown for all 12 cells.

Reproduce with:

    uv run --with seaborn python scripts/efficiency_boxplots.py

Read-only on the experiment databases; never touches outputs/factorial_rerun_20260624.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

REPO = Path(__file__).resolve().parents[1]
FACTORIAL = REPO / "outputs" / "factorial"
FIG_DIR = REPO / "outputs" / "analysis" / "figures"
STATS_MD = REPO / "outputs" / "analysis" / "efficiency_stats_20260625.md"

MODELS = ["glm-4.5-air", "glm-5.2", "minimax-m3"]
PARADIGMS = ["agentic", "static"]
AUGS = ["none", "tools"]

# Metric column -> (label, log-scale y axis?)
METRICS = {
    "iterations": ("Search iterations (#)", False),
    "latency_s": ("Latency (s)", True),
    "total_tokens": ("Total tokens (input + output)", True),
}

# Documented list pricing (USD per 1M tokens), in_miss / cached / output.
# glm-5.2 and glm-4.5-air: official docs.z.ai list rates (cached-input storage
# is limited-time free, not modeled). minimax-m3: platform.minimax.io list rate
# (a 50% launch promo would halve it). All real per-question token splits
# (input / cached_input subset / output) come from the judged factorial DBs.
PRICING = {
    "glm-5.2": (1.40, 0.26, 4.40),       # docs.z.ai
    "minimax-m3": (0.60, 0.12, 2.40),    # platform.minimax.io list (promo would halve)
    "glm-4.5-air": (0.20, 0.03, 1.10),   # docs.z.ai
}


def load_all() -> pd.DataFrame:
    frames = []
    for model in MODELS:
        for paradigm in PARADIGMS:
            for aug in AUGS:
                cell = f"{model}__{paradigm}__{aug}"
                db = FACTORIAL / cell / "results.sqlite"
                if not db.exists():
                    raise FileNotFoundError(f"missing cell db: {db}")
                uri = f"file:{db}?mode=ro"
                with sqlite3.connect(uri, uri=True) as con:
                    df = pd.read_sql_query(
                        "SELECT question_id, repeat_idx, status, abstention, "
                        "num_iterations, latency_s, input_tokens, "
                        "cached_input_tokens, output_tokens "
                        "FROM results",
                        con,
                    )
                df["model"] = model
                df["paradigm"] = paradigm
                df["augmentation"] = aug
                df["cell"] = cell
                frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out["iterations"] = out["num_iterations"]
    out["total_tokens"] = out["input_tokens"].fillna(0) + out["output_tokens"].fillna(0)
    return out


def _fmt(x: float, decimals: int = 2) -> str:
    if pd.isna(x):
        return "n/a"
    if decimals == 0:
        return f"{x:,.0f}"
    return f"{x:,.{decimals}f}"


def stats_table(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    rows = []
    for keys, g in df.groupby(group_cols):
        keys = keys if isinstance(keys, tuple) else (keys,)
        rec = dict(zip(group_cols, keys))
        rec["n"] = len(g)
        for col, decimals in (("iterations", 1), ("latency_s", 2), ("total_tokens", 0)):
            rec[f"{col}_mean"] = g[col].mean()
            rec[f"{col}_median"] = g[col].median()
            rec[f"{col}_var"] = g[col].var(ddof=1)
            rec[f"{col}_std"] = g[col].std(ddof=1)
        rows.append(rec)
    return pd.DataFrame(rows)


def md_metric_table(tbl: pd.DataFrame, key_cols: list[str], col: str, decimals: int) -> str:
    header = "| " + " | ".join(key_cols + ["n", "mean", "median", "variance", "std"]) + " |"
    sep = "|" + "|".join(["---"] * len(key_cols) + ["---:"] * 5) + "|"
    lines = [header, sep]
    for _, r in tbl.iterrows():
        keys = [str(r[k]) for k in key_cols]
        vals = [
            _fmt(r[f"{col}_mean"], decimals),
            _fmt(r[f"{col}_median"], decimals),
            _fmt(r[f"{col}_var"], decimals),
            _fmt(r[f"{col}_std"], decimals),
        ]
        lines.append("| " + " | ".join(keys + [str(int(r["n"]))] + vals) + " |")
    return "\n".join(lines)


def make_boxplots(agentic: pd.DataFrame) -> list[Path]:
    sns.set_theme(style="whitegrid", context="paper", font_scale=1.1)
    palette = sns.color_palette("colorblind", n_colors=2)
    paths: list[Path] = []

    # Combined 1x3 panel.
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
    for ax, (col, (label, logy)) in zip(axes, METRICS.items()):
        sns.boxplot(
            data=agentic, x="model", y=col, hue="augmentation",
            order=MODELS, hue_order=AUGS, palette=palette,
            fliersize=1.5, linewidth=1.0, ax=ax,
        )
        if logy:
            ax.set_yscale("log")
        ax.set_xlabel("")
        ax.set_ylabel(label)
        ax.tick_params(axis="x", rotation=15)
        if ax is not axes[-1]:
            ax.legend_.remove()
        else:
            ax.legend(title="augmentation", loc="upper left", frameon=True)
    fig.suptitle("Agentic IR efficiency by model (514 questions per cell)", y=1.02)
    fig.tight_layout()
    for ext in ("pdf", "png"):
        p = FIG_DIR / f"efficiency_boxplots.{ext}"
        fig.savefig(p, bbox_inches="tight", dpi=300)
        paths.append(p)
    plt.close(fig)

    # Individual per-metric figures.
    for col, (label, logy) in METRICS.items():
        fig, ax = plt.subplots(figsize=(5.2, 4.2))
        sns.boxplot(
            data=agentic, x="model", y=col, hue="augmentation",
            order=MODELS, hue_order=AUGS, palette=palette,
            fliersize=1.5, linewidth=1.0, ax=ax,
        )
        if logy:
            ax.set_yscale("log")
        ax.set_xlabel("")
        ax.set_ylabel(label)
        ax.tick_params(axis="x", rotation=15)
        ax.legend(title="augmentation", loc="upper left", frameon=True)
        fig.tight_layout()
        stem = "tokens" if col == "total_tokens" else col.replace("_s", "")
        for ext in ("pdf", "png"):
            p = FIG_DIR / f"efficiency_box_{stem}.{ext}"
            fig.savefig(p, bbox_inches="tight", dpi=300)
            paths.append(p)
        plt.close(fig)
    return paths


def main() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    df = load_all()

    done = df[df["status"] == "done"].copy()
    counts = df.groupby("cell").size()
    done_counts = done.groupby("cell").size()
    flagged = [c for c in counts.index if counts[c] != 514 or done_counts.get(c, 0) != 514]

    agentic = done[done["paradigm"] == "agentic"].copy()

    per_model = stats_table(agentic, ["model"]).set_index("model").loc[MODELS].reset_index()
    per_cell_all = stats_table(done, ["model", "paradigm", "augmentation"])
    per_cell_all = per_cell_all.sort_values(["model", "paradigm", "augmentation"]).reset_index(drop=True)
    per_model_aug = stats_table(agentic, ["model", "augmentation"]).sort_values(
        ["model", "augmentation"]
    ).reset_index(drop=True)

    paths = make_boxplots(agentic)

    # Optional USD cost per question for models with documented list pricing.
    usd_rows = []
    for model in MODELS:
        price = PRICING[model]
        g = agentic[agentic["model"] == model]
        if price is None:
            usd_rows.append((model, "rate not documented in repo (TBC)", None, None))
            continue
        in_miss, cached, out = price
        cost = (
            (g["input_tokens"].fillna(0) - g["cached_input_tokens"].fillna(0)) * in_miss / 1e6
            + g["cached_input_tokens"].fillna(0) * cached / 1e6
            + g["output_tokens"].fillna(0) * out / 1e6
        )
        # Upper bound: every input token billed at the cache-miss rate (no cache discount).
        cost_nocache = (
            g["input_tokens"].fillna(0) * in_miss / 1e6
            + g["output_tokens"].fillna(0) * out / 1e6
        )
        usd_rows.append((
            model, f"{in_miss}/{cached}/{out}",
            cost.mean(), cost.median(),
            cost_nocache.mean(), cost_nocache.median(),
        ))

    lines: list[str] = []
    lines.append("# Factorial efficiency stats: iterations / latency / cost (R2 C4-C5)")
    lines.append("")
    lines.append("Generated by `scripts/efficiency_boxplots.py` from the canonical judged")
    lines.append("factorial cells (`outputs/factorial/<cell>/results.sqlite`). The running")
    lines.append("stochasticity rerun (`outputs/factorial_rerun_20260624/`) is excluded.")
    lines.append("")
    lines.append("## Metric definitions")
    lines.append("")
    lines.append("- iterations: `num_iterations` (agentic search steps per question).")
    lines.append("- latency: `latency_s` (wall-clock seconds per question).")
    lines.append("- total tokens: `input_tokens + output_tokens` per question. Used as the")
    lines.append("  pricing-free cost proxy (\"COST/tokens\"); cached input is a subset of input.")
    lines.append("")
    lines.append("## Cell inclusion")
    lines.append("")
    lines.append("Figures use AGENTIC cells only (pooled or split by augmentation). The static")
    lines.append("cells are degenerate here (one iteration by construction, heavy abstention),")
    lines.append("so they are reported in the per-cell table below but kept out of the efficiency")
    lines.append("figures. Each cell has 514 questions, one repeat (`repeat_idx=0`).")
    lines.append("")
    if flagged:
        lines.append(f"Caveat: cells not at 514 done rows: {flagged}.")
    else:
        lines.append("Sanity check: all 12 cells have exactly 514 rows, all `status='done'`.")
    lines.append("")
    lines.append("## Per-model summary (agentic, pooled over none+tools)")
    lines.append("")
    for col, dec, name in (
        ("iterations", 1, "Iterations"),
        ("latency_s", 2, "Latency (s)"),
        ("total_tokens", 0, "Total tokens"),
    ):
        lines.append(f"### {name}")
        lines.append("")
        lines.append(md_metric_table(per_model, ["model"], col, dec))
        lines.append("")
    lines.append("## Per-model x augmentation (agentic)")
    lines.append("")
    for col, dec, name in (
        ("iterations", 1, "Iterations"),
        ("latency_s", 2, "Latency (s)"),
        ("total_tokens", 0, "Total tokens"),
    ):
        lines.append(f"### {name}")
        lines.append("")
        lines.append(md_metric_table(per_model_aug, ["model", "augmentation"], col, dec))
        lines.append("")
    lines.append("## Full per-cell breakdown (all 12 cells)")
    lines.append("")
    for col, dec, name in (
        ("iterations", 1, "Iterations"),
        ("latency_s", 2, "Latency (s)"),
        ("total_tokens", 0, "Total tokens"),
    ):
        lines.append(f"### {name}")
        lines.append("")
        lines.append(md_metric_table(per_cell_all, ["model", "paradigm", "augmentation"], col, dec))
        lines.append("")
    lines.append("## USD cost per question (agentic, official list pricing)")
    lines.append("")
    lines.append("Rate source (USD per 1M tokens, in-miss / cached / output): glm-5.2 and")
    lines.append("glm-4.5-air at official docs.z.ai list rates (1.40/0.26/4.40 and")
    lines.append("0.20/0.03/1.10); minimax-m3 at platform.minimax.io list rate (0.60/0.12/2.40,")
    lines.append("a 50% launch promo would halve it). Cached-input storage is limited-time free")
    lines.append("and not modeled.")
    lines.append("")
    lines.append("Caching assumption: the `cached-input` column uses each question's real")
    lines.append("`cached_input_tokens` (a subset of input) billed at the cache-hit rate and the")
    lines.append("rest at the cache-miss rate. In agentic search a large context is reused across")
    lines.append("iterations, so roughly 90% of input tokens are cache reads, which is why the")
    lines.append("cached-input cost is far below the no-cache figure. The `no-cache upper bound`")
    lines.append("column bills every input token at the cache-miss rate, i.e. the cost if no")
    lines.append("prompt caching applied. Cost is right-skewed, so the median is the honest")
    lines.append("typical-case figure and the mean is inflated by a few expensive questions.")
    lines.append("")
    lines.append("| model | rate (in/cache/out per 1M) | cached-input mean USD/q | cached-input median USD/q | no-cache mean USD/q | no-cache median USD/q |")
    lines.append("|---|---|---:|---:|---:|---:|")
    for model, rate, mean_usd, med_usd, mean_nc, med_nc in usd_rows:
        mu = "n/a" if mean_usd is None else f"${mean_usd:.4f}"
        md = "n/a" if med_usd is None else f"${med_usd:.4f}"
        mnc = "n/a" if mean_nc is None else f"${mean_nc:.4f}"
        mdnc = "n/a" if med_nc is None else f"${med_nc:.4f}"
        lines.append(f"| {model} | {rate} | {mu} | {md} | {mnc} | {mdnc} |")
    lines.append("")
    lines.append("## Figures")
    lines.append("")
    for p in paths:
        lines.append(f"- `{p.relative_to(REPO)}`")
    lines.append("")

    STATS_MD.write_text("\n".join(lines))
    print(f"wrote {STATS_MD}")
    for p in paths:
        print(f"wrote {p}")
    print("\nper-model agentic summary:")
    print(per_model[["model", "n", "iterations_mean", "iterations_median",
                     "latency_s_mean", "latency_s_median",
                     "total_tokens_mean", "total_tokens_median"]].to_string(index=False))


if __name__ == "__main__":
    main()
