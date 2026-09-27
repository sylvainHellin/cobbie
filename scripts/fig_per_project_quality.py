"""Publication figure: per-project accuracy vs BIM-model quality (validation issues).

Reads outputs/analysis/per_project_accuracy_20260629.csv and writes
figure_per_project_quality.{pdf,png} for the journal paper.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import optimize

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "outputs/analysis/per_project_accuracy_20260629.csv"
OUT_DIR = Path.home() / "code/tum/1st-journal-paper/overleaf-revision/assets"

LABELED = {
    "molio": (-44, -3),
    "hitos": (-10, 11),
    "sixty5": (12, -3),
    "wbdg_office": (-14, 13),
    "digital_hub": (10, -13),
}
PRETTY = {
    "molio": "molio",
    "hitos": "hitos",
    "sixty5": "sixty5",
    "wbdg_office": "wbdg office",
    "digital_hub": "digital hub",
}


def main() -> None:
    df = pd.read_csv(CSV)
    x = np.log1p(df["total_issues"].to_numpy(dtype=float))
    y = df["accuracy"].to_numpy(dtype=float) * 100.0
    n = df["n_questions"].to_numpy(dtype=float)

    # binomial-logistic fit, linear in log1p(issues) on the log-odds scale
    # (same functional form as the paper's logistic-regression covariate)
    k = np.round(df["accuracy"].to_numpy() * n)

    def nll(b: np.ndarray) -> float:
        p = 1.0 / (1.0 + np.exp(-(b[0] + b[1] * x)))
        p = np.clip(p, 1e-9, 1 - 1e-9)
        return -(k * np.log(p) + (n - k) * np.log(1 - p)).sum()

    b0, b1 = optimize.minimize(nll, [1.5, -0.2], method="Nelder-Mead").x

    plt.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Helvetica", "Arial", "DejaVu Sans"],
            "font.size": 9,
            "axes.linewidth": 0.8,
            "pdf.fonttype": 42,
        }
    )

    fig, ax = plt.subplots(figsize=(5.0, 3.4))

    # fitted logistic curve
    xs = np.linspace(x.min(), x.max(), 200)
    ax.plot(
        xs,
        100.0 / (1.0 + np.exp(-(b0 + b1 * xs))),
        ls="--",
        lw=1.2,
        color="#E37222",  # TUM orange
        zorder=2,
    )

    # bubbles: area proportional to number of questions
    ax.scatter(
        x,
        y,
        s=n * 7.0,
        facecolor="#0065BD",  # TUM blue
        alpha=0.60,
        edgecolor="white",
        linewidth=0.8,
        zorder=3,
    )

    # label notable projects
    for _, row in df.iterrows():
        name = row["project"]
        if name not in LABELED:
            continue
        dx, dy = LABELED[name]
        ax.annotate(
            PRETTY[name],
            (np.log1p(row["total_issues"]), row["accuracy"] * 100.0),
            textcoords="offset points",
            xytext=(dx, dy),
            fontsize=7.5,
            color="#444444",
            zorder=4,
        )

    # x ticks at round issue counts, positioned at log1p
    ticks = [0, 10, 100, 1000]
    ax.set_xticks([np.log1p(t) for t in ticks])
    ax.set_xticklabels([f"{t:,}" for t in ticks])

    ax.set_xlabel("BIM-model validation issues (log scale)")
    ax.set_ylabel("Per-project accuracy (%)")
    ax.set_ylim(0, 105)
    ax.set_xlim(x.min() - 0.45, x.max() + 0.45)
    ax.yaxis.grid(True, lw=0.4, color="#DDDDDD", zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    fig.tight_layout()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT_DIR / "figure_per_project_quality.pdf")
    fig.savefig(OUT_DIR / "figure_per_project_quality.png", dpi=300)
    print(f"logistic fit: b0={b0:.2f}, b1={b1:.3f}; wrote to {OUT_DIR}")


if __name__ == "__main__":
    main()
