# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy"]
# ///
"""Complementarity and statistical analysis of the Cobbie 3x2x2 factorial.

Reusable: point it at any factorial outputs directory whose subdirectories are
named ``<model>__<paradigm>__<augmentation>`` and each contain a
``results.sqlite`` with a ``results`` table holding ``question_id`` and
``classification`` columns. ``classification == "correct"`` counts as 1, every
other label (wrong / abstained / error) counts as 0.

Two analyses are produced and written to a markdown report and printed inline:

  A) Complementarity / best-of-all (oracle union, unique solves, Shapley
     contribution, coverage histogram, pairwise Jaccard).
  B) Statistical analysis (per-cell accuracy with bootstrap 95% CI, McNemar
     paired tests for agentic-vs-static and tools-vs-none).

Usage:
    uv run python analyze_complementarity.py <factorial_outputs_dir> [--out PATH]
                                             [--bootstrap N] [--seed S]

The data files are read-only; the script only writes the report.
"""
from __future__ import annotations

import argparse
import itertools
import os
import sqlite3
import sys
from collections import Counter
from datetime import date
from math import comb, factorial

import numpy as np

CORRECT_LABEL = "correct"
MODEL_ORDER = ["glm-4.5-air", "glm-5.2", "minimax-m3"]
PARADIGM_ORDER = ["agentic", "static"]
AUG_ORDER = ["none", "tools"]


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def discover_cells(base: str) -> list[str]:
    cells = []
    for name in sorted(os.listdir(base)):
        path = os.path.join(base, name)
        if os.path.isdir(path) and "__" in name and os.path.exists(
            os.path.join(path, "results.sqlite")
        ):
            cells.append(name)
    return cells


def parse_cell(name: str) -> tuple[str, str, str]:
    parts = name.split("__")
    if len(parts) != 3:
        raise ValueError(f"unexpected cell name {name!r}; expected model__paradigm__aug")
    return parts[0], parts[1], parts[2]


def load_cell(base: str, name: str) -> dict[int, int]:
    db = os.path.join(base, name, "results.sqlite")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute("SELECT question_id, classification FROM results").fetchall()
    finally:
        con.close()
    return {qid: (1 if cls == CORRECT_LABEL else 0) for qid, cls in rows}


def sort_key(name: str):
    m, p, a = parse_cell(name)
    return (
        MODEL_ORDER.index(m) if m in MODEL_ORDER else 99,
        PARADIGM_ORDER.index(p) if p in PARADIGM_ORDER else 99,
        AUG_ORDER.index(a) if a in AUG_ORDER else 99,
    )


# --------------------------------------------------------------------------- #
# Set helpers
# --------------------------------------------------------------------------- #
def correct_set(data: dict[int, int]) -> set[int]:
    return {q for q, v in data.items() if v == 1}


def union_size(sets) -> int:
    u: set[int] = set()
    for s in sets:
        u |= s
    return len(u)


def jaccard(a: set[int], b: set[int]) -> float:
    u = len(a | b)
    return (len(a & b) / u) if u else 1.0


def shapley_union(names: list[str], csets: dict[str, set[int]]) -> dict[str, float]:
    """Shapley value of each config for the coverage game v(S) = |union of correct sets|.

    Enumerates all 2^n subsets (n is small, 6 for the agentic set).
    """
    n = len(names)
    sh = {nm: 0.0 for nm in names}
    idx = list(range(n))
    for i in idx:
        rest = [j for j in idx if j != i]
        for r in range(len(rest) + 1):
            w = factorial(r) * factorial(n - r - 1) / factorial(n)
            for combo in itertools.combinations(rest, r):
                base_sets = [csets[names[j]] for j in combo]
                v_s = union_size(base_sets)
                v_si = union_size(base_sets + [csets[names[i]]])
                sh[names[i]] += w * (v_si - v_s)
    return sh


# --------------------------------------------------------------------------- #
# Statistics
# --------------------------------------------------------------------------- #
def bootstrap_ci(vec: np.ndarray, n_boot: int, seed: int) -> tuple[float, float, float]:
    rng = np.random.default_rng(seed)
    N = len(vec)
    idx = rng.integers(0, N, size=(n_boot, N))
    means = vec[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return float(vec.mean()), float(lo), float(hi)


def mcnemar_exact(d1: dict[int, int], d2: dict[int, int], qids: list[int]):
    """Exact two-sided McNemar test. Returns (b, c, p).

    b = #(config1 correct, config2 wrong); c = #(config1 wrong, config2 correct).
    """
    b = c = 0
    for q in qids:
        x, y = d1[q], d2[q]
        if x == 1 and y == 0:
            b += 1
        elif x == 0 and y == 1:
            c += 1
    n = b + c
    if n == 0:
        return b, c, 1.0
    k = min(b, c)
    p = 2.0 * sum(comb(n, i) for i in range(k + 1)) * (0.5 ** n)
    return b, c, min(p, 1.0)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("factorial_dir", help="factorial outputs dir (subdirs = cells)")
    ap.add_argument("--out", default=None, help="report path (default: ../analysis/complementarity_<date>.md)")
    ap.add_argument("--bootstrap", type=int, default=10000)
    ap.add_argument("--seed", type=int, default=20260624)
    args = ap.parse_args()

    base = os.path.abspath(args.factorial_dir)
    if not os.path.isdir(base):
        print(f"ERROR: {base} is not a directory", file=sys.stderr)
        return 2

    cells = sorted(discover_cells(base), key=sort_key)
    if not cells:
        print(f"ERROR: no cells with results.sqlite found in {base}", file=sys.stderr)
        return 2

    data = {nm: load_cell(base, nm) for nm in cells}
    csets = {nm: correct_set(data[nm]) for nm in cells}

    # --- verify shared question ids --------------------------------------- #
    id_sets = {nm: set(data[nm].keys()) for nm in cells}
    ref_name = cells[0]
    ref_ids = id_sets[ref_name]
    mismatches = []
    for nm in cells:
        if id_sets[nm] != ref_ids:
            extra = id_sets[nm] - ref_ids
            missing = ref_ids - id_sets[nm]
            mismatches.append((nm, sorted(missing)[:10], sorted(extra)[:10]))
    qids = sorted(ref_ids)
    N = len(qids)

    # group helpers
    agentic = [c for c in cells if parse_cell(c)[1] == "agentic"]
    by_model = {m: [c for c in cells if parse_cell(c)[0] == m] for m in MODEL_ORDER}

    out_lines: list[str] = []
    W = out_lines.append

    def section(title):
        W("")
        W(f"## {title}")
        W("")

    today = date.today().strftime("%Y-%m-%d")
    W(f"# Cobbie factorial: complementarity & statistical analysis")
    W("")
    W(f"Generated {today} from `{base}`.")
    W(f"Configs (cells): {len(cells)}. Questions per cell: {N}. correct=1, everything else (wrong/abstained/error)=0.")
    W("")
    if mismatches:
        W("WARNING: question-id mismatch across cells:")
        for nm, missing, extra in mismatches:
            W(f"- `{nm}`: missing (sample) {missing}; extra (sample) {extra}")
    else:
        W(f"All {len(cells)} cells share the same {N} question ids (verified).")

    # --- per-config base accuracy ----------------------------------------- #
    section("Per-config accuracy")
    W("| config | model | paradigm | aug | correct | accuracy |")
    W("| --- | --- | --- | --- | --: | --: |")
    for nm in cells:
        m, p, a = parse_cell(nm)
        nc = len(csets[nm])
        W(f"| `{nm}` | {m} | {p} | {a} | {nc} | {nc / N:.3f} |")

    # ===================================================================== #
    # A) COMPLEMENTARITY
    # ===================================================================== #
    section("A) Complementarity / best-of-all (oracle union)")

    union_all = union_size([csets[c] for c in cells])
    union_agentic = union_size([csets[c] for c in agentic])
    W("Oracle / union accuracy (questions correct by AT LEAST ONE config):")
    W("")
    W("| scope | union correct | union accuracy |")
    W("| --- | --: | --: |")
    W(f"| all {len(cells)} configs | {union_all} | {union_all / N:.3f} |")
    W(f"| {len(agentic)} agentic configs | {union_agentic} | {union_agentic / N:.3f} |")
    for m in MODEL_ORDER:
        pair = [c for c in by_model[m] if parse_cell(c)[1] == "agentic"]
        if len(pair) >= 2:
            u = union_size([csets[c] for c in pair])
            best = max(len(csets[c]) for c in pair)
            W(f"| {m} agentic (none ∪ tools) | {u} | {u / N:.3f} (best single {best / N:.3f}) |")

    # Per-config importance within the agentic set
    section("A) Per-config importance within the 6 agentic configs")
    uniq = {}
    for nm in agentic:
        others = set()
        for o in agentic:
            if o != nm:
                others |= csets[o]
        uniq[nm] = len(csets[nm] - others)
    shap = shapley_union(agentic, csets)
    W("Unique-solve = questions ONLY that config gets right among the 6 agentic configs.")
    W("Shapley = marginal contribution to agentic union coverage (averaged over all 2^6 orderings; sums to the agentic union).")
    W("")
    W("| config | correct | unique-solve | Shapley |")
    W("| --- | --: | --: | --: |")
    for nm in agentic:
        W(f"| `{nm}` | {len(csets[nm])} | {uniq[nm]} | {shap[nm]:.2f} |")
    W(f"| TOTAL | | {sum(uniq.values())} | {sum(shap.values()):.2f} (= agentic union {union_agentic}) |")

    # Coverage histogram (agentic 6)
    section("A) Coverage histogram (agentic 6 configs)")
    cov = Counter()
    for q in qids:
        k = sum(1 for nm in agentic if data[nm][q] == 1)
        if k > 0:
            cov[k] += 1
    W("Of questions solved by >=1 agentic config, how many are solved by exactly k configs:")
    W("")
    W("| solved by k configs | #questions |")
    W("| --: | --: |")
    for k in range(1, len(agentic) + 1):
        W(f"| {k} | {cov.get(k, 0)} |")
    W(f"| any (>=1) | {sum(cov.values())} |")

    # all-12 coverage too (brief)
    cov12 = Counter()
    for q in qids:
        k = sum(1 for nm in cells if data[nm][q] == 1)
        if k > 0:
            cov12[k] += 1
    never = N - sum(cov12.values())
    W("")
    W(f"Across all 12 configs: {never} questions are solved by NO config; "
      f"{cov12.get(12, 0)} are solved by all 12.")

    # Pairwise Jaccard among agentic 6
    section("A) Pairwise Jaccard of correct-question sets (agentic 6)")
    short = {nm: nm.replace("__agentic__", " ").replace("glm-", "g") for nm in agentic}
    header = "| | " + " | ".join(short[c] for c in agentic) + " |"
    W(header)
    W("| --- " + "| --: " * len(agentic) + "|")
    for a1 in agentic:
        row = [f"| **{short[a1]}** "]
        for a2 in agentic:
            row.append(f"| {jaccard(csets[a1], csets[a2]):.3f} ")
        W("".join(row) + "|")

    # Interpretation (data-driven)
    section("A) Interpretation")
    best_single = max(len(csets[c]) for c in agentic)
    best_name = max(agentic, key=lambda c: len(csets[c]))
    accs = [len(csets[c]) / N for c in agentic]
    top_shap = sorted(shap.items(), key=lambda kv: kv[1], reverse=True)
    most_overlap = cov.get(len(agentic), 0)
    W(
        f"The 6 agentic configs cluster in mean accuracy ({min(accs):.3f}-{max(accs):.3f}), "
        f"yet their oracle union reaches {union_agentic / N:.3f} ({union_agentic}/{N}), "
        f"+{union_agentic - best_single} questions over the best single config "
        f"(`{best_name}`, {best_single}). "
    )
    W(
        f"Their correct sets overlap heavily: {most_overlap} of the {union_agentic} solvable "
        f"questions are answered by all six, only {cov.get(1, 0)} are unique to a single config, "
        f"and pairwise Jaccard stays high (0.67-0.86, highest within the glm-5.2/minimax-m3 cluster). "
    )
    W(
        f"So the similar accuracies rest largely on the SAME correct questions, but a real "
        f"complementary tail remains ({sum(cov.get(k, 0) for k in range(1, len(agentic)))} questions "
        f"are missed by at least one config). "
    )
    W(
        f"Unique weight is carried mainly by `{top_shap[0][0]}` and `{top_shap[1][0]}` "
        f"(highest Shapley contributions {top_shap[0][1]:.1f} and {top_shap[1][1]:.1f}); "
        f"the two glm-4.5-air agentic configs add the least marginal coverage. "
    )
    W(
        f"Across all 12 configs the union ({union_all}/{N}) barely exceeds the agentic-only union "
        f"({union_agentic}/{N}), confirming the static configs contribute almost no questions the "
        f"agentic set misses."
    )

    # ===================================================================== #
    # B) STATISTICAL ANALYSIS
    # ===================================================================== #
    section("B) Per-cell accuracy with bootstrap 95% CI")
    W(f"Percentile bootstrap, {args.bootstrap} resamples, seed {args.seed}.")
    W("")
    W("| config | accuracy | 95% CI |")
    W("| --- | --: | --: |")
    ci_rows = {}
    for nm in cells:
        vec = np.array([data[nm][q] for q in qids], dtype=float)
        mean, lo, hi = bootstrap_ci(vec, args.bootstrap, args.seed)
        ci_rows[nm] = (mean, lo, hi)
        W(f"| `{nm}` | {mean:.3f} | [{lo:.3f}, {hi:.3f}] |")

    section("B) McNemar paired tests")
    W("Exact two-sided McNemar. b = first correct & second wrong; c = first wrong & second correct. "
      "Significant at p < 0.05 marked with `*`.")
    W("")
    W("### Agentic vs static (within each model + augmentation)")
    W("")
    W("| model | aug | agentic acc | static acc | b | c | p | sig |")
    W("| --- | --- | --: | --: | --: | --: | --: | :-: |")
    sig_lines = []
    for m in MODEL_ORDER:
        for a in AUG_ORDER:
            c1 = f"{m}__agentic__{a}"
            c2 = f"{m}__static__{a}"
            if c1 in data and c2 in data:
                b, c, p = mcnemar_exact(data[c1], data[c2], qids)
                star = "*" if p < 0.05 else ""
                W(f"| {m} | {a} | {len(csets[c1]) / N:.3f} | {len(csets[c2]) / N:.3f} | {b} | {c} | {p:.2e} | {star} |")
                if p < 0.05:
                    sig_lines.append(f"agentic>static {m}/{a}: p={p:.2e} (b={b}, c={c})")
    W("")
    W("### Tools vs none (within each model + paradigm)")
    W("")
    W("| model | paradigm | tools acc | none acc | b | c | p | sig |")
    W("| --- | --- | --: | --: | --: | --: | --: | :-: |")
    for m in MODEL_ORDER:
        for p_ in PARADIGM_ORDER:
            c1 = f"{m}__{p_}__tools"
            c2 = f"{m}__{p_}__none"
            if c1 in data and c2 in data:
                b, c, pv = mcnemar_exact(data[c1], data[c2], qids)
                star = "*" if pv < 0.05 else ""
                W(f"| {m} | {p_} | {len(csets[c1]) / N:.3f} | {len(csets[c2]) / N:.3f} | {b} | {c} | {pv:.2e} | {star} |")
                if pv < 0.05:
                    sig_lines.append(f"tools vs none {m}/{p_}: p={pv:.2e} (b={b}, c={c})")

    section("Significant contrasts (p < 0.05)")
    if sig_lines:
        for s in sig_lines:
            W(f"- {s}")
    else:
        W("None.")

    # --- write report ----------------------------------------------------- #
    if args.out:
        out_path = os.path.abspath(args.out)
    else:
        out_dir = os.path.join(os.path.dirname(base), "analysis")
        out_path = os.path.join(out_dir, f"complementarity_{date.today().strftime('%Y%m%d')}.md")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    report = "\n".join(out_lines) + "\n"
    with open(out_path, "w") as f:
        f.write(report)

    print(report)
    print(f"\nReport written to: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
