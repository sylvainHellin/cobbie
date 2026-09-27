# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Cell-by-cell comparator for two Cobbie factorial runs.

Diffs TWO factorial output directories (``BASE_A`` vs ``BASE_B``) whose
subdirectories are named ``<model>__<paradigm>__<augmentation>`` and each
contain a ``results.sqlite`` with a ``results`` table holding ``question_id``,
``classification`` (``correct`` | ``wrong`` | ``abstained`` | ``error`` |
NULL-if-unjudged) and ``predicted`` columns.

It quantifies, per common cell:

  (a) per-cell average performance change (accuracy / breakdown / abstention),
  (b) a question-by-question flip analysis (3x3 transition matrix + headline
      counts) over the comparable intersection of question ids.

Intended uses (run after judging completes):
  * no-thinking rerun vs original  -> stochasticity of the pipeline
  * thinking rerun vs original     -> the effect of enabling thinking

Comparison rules
----------------
* Cells compared = intersection of cell dir names present in BOTH bases (each
  with a ``results.sqlite``), unless ``--cells`` is given.
* For each cell we INNER-JOIN on ``question_id`` (intersection of ids present in
  both sides).
* A row is COMPARABLE only if its ``classification`` is one of
  {correct, wrong, abstained} on BOTH sides. Rows that are NULL/unjudged or
  ``error`` on either side are excluded from accuracy + flips and reported
  separately (NULL is never counted as wrong).
* Accuracy convention matches the rest of the repo: correct = 1, else 0 (here
  over the comparable set only).

Usage
-----
    uv run python scripts/compare_runs.py BASE_A BASE_B \
        [--cells C1 C2 ...] [--out report.md] [--csv changes.csv]

The result DBs are opened read-only; this script only writes the report / CSV
you point it at. A guarded self-test (no DBs needed) runs when the environment
variable ``COMPARE_RUNS_SELFTEST=1`` is set.
"""
from __future__ import annotations

import argparse
import csv
import os
import sqlite3
import sys
from datetime import date

# Labels that participate in accuracy + flip analysis, in matrix row/col order.
CLASSES = ["correct", "wrong", "abstained"]
CORRECT_LABEL = "correct"
ABSTAIN_LABEL = "abstained"
# Labels excluded from the comparable set (reported separately).
EXCLUDED = {"error", "unjudged"}


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def discover_cells(base: str) -> list[str]:
    """Cell dir names (``model__paradigm__aug``) that have a results.sqlite."""
    cells = []
    if not os.path.isdir(base):
        return cells
    for name in sorted(os.listdir(base)):
        path = os.path.join(base, name)
        if (
            os.path.isdir(path)
            and "__" in name
            and os.path.exists(os.path.join(path, "results.sqlite"))
        ):
            cells.append(name)
    return cells


def _norm_label(classification, error) -> str:
    """Map a raw row to one of correct/wrong/abstained/error/unjudged."""
    if classification is None or (isinstance(classification, str) and classification.strip() == ""):
        # An explicit error row that was never judged still counts as 'error'.
        return "error" if error else "unjudged"
    cls = classification.strip().lower()
    if cls in CLASSES:
        return cls
    if cls == "error":
        return "error"
    # Unknown label: treat as unjudged so it is flagged, not silently scored.
    return "unjudged"


def load_cell(base: str, cell: str) -> dict[int, dict]:
    """Return {question_id: {'label', 'predicted'}} for a cell (read-only)."""
    db = os.path.join(base, cell, "results.sqlite")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "SELECT question_id, classification, error, predicted FROM results"
        ).fetchall()
    finally:
        con.close()
    out: dict[int, dict] = {}
    for qid, classification, error, predicted in rows:
        out[qid] = {
            "label": _norm_label(classification, error),
            "predicted": predicted,
        }
    return out


def _snippet(text, n: int = 160) -> str:
    if not text:
        return ""
    s = " ".join(str(text).split())
    return s[:n] + ("…" if len(s) > n else "")


# --------------------------------------------------------------------------- #
# Comparison core
# --------------------------------------------------------------------------- #
def compare_cell(a: dict[int, dict], b: dict[int, dict]) -> dict:
    """Compare one cell. ``a``/``b`` map qid -> {'label', 'predicted'}.

    Returns a dict with counts, per-side breakdowns, a 3x3 transition matrix
    (A rows -> B cols over CLASSES), flip headlines and per-question diffs.
    """
    ids_a, ids_b = set(a), set(b)
    inter = ids_a & ids_b

    # Drop bookkeeping over the intersection.
    dropped_unjudged = 0  # NULL/unknown on either side
    dropped_error = 0     # error on either side (and not already unjudged)
    comparable: list[int] = []
    for qid in inter:
        la, lb = a[qid]["label"], b[qid]["label"]
        if la == "unjudged" or lb == "unjudged":
            dropped_unjudged += 1
        elif la == "error" or lb == "error":
            dropped_error += 1
        else:
            comparable.append(qid)
    comparable.sort()

    # 3x3 transition matrix: matrix[i][j] = #(A==CLASSES[i] and B==CLASSES[j]).
    idx = {c: i for i, c in enumerate(CLASSES)}
    matrix = [[0, 0, 0] for _ in CLASSES]
    diffs: list[dict] = []
    for qid in comparable:
        la, lb = a[qid]["label"], b[qid]["label"]
        matrix[idx[la]][idx[lb]] += 1
        if la != lb:
            diffs.append(
                {
                    "question_id": qid,
                    "class_A": la,
                    "class_B": lb,
                    "predicted_A": _snippet(a[qid]["predicted"]),
                    "predicted_B": _snippet(b[qid]["predicted"]),
                }
            )

    n_cmp = len(comparable)
    # Per-side breakdowns over the comparable set (row/col sums of the matrix).
    counts_a = {c: sum(matrix[idx[c]]) for c in CLASSES}
    counts_b = {c: sum(matrix[r][idx[c]] for r in range(len(CLASSES))) for c in CLASSES}

    acc_a = counts_a[CORRECT_LABEL] / n_cmp if n_cmp else 0.0
    acc_b = counts_b[CORRECT_LABEL] / n_cmp if n_cmp else 0.0
    abst_a = counts_a[ABSTAIN_LABEL] / n_cmp if n_cmp else 0.0
    abst_b = counts_b[ABSTAIN_LABEL] / n_cmp if n_cmp else 0.0

    off_diag = sum(
        matrix[i][j] for i in range(len(CLASSES)) for j in range(len(CLASSES)) if i != j
    )

    ci, wi, ai = idx["correct"], idx["wrong"], idx["abstained"]
    return {
        "n_A": len(a),
        "n_B": len(b),
        "n_intersection": len(inter),
        "dropped_unjudged": dropped_unjudged,
        "dropped_error": dropped_error,
        "n_comparable": n_cmp,
        "counts_A": counts_a,
        "counts_B": counts_b,
        "accuracy_A": acc_a,
        "accuracy_B": acc_b,
        "accuracy_delta": acc_b - acc_a,
        "abstention_A": abst_a,
        "abstention_B": abst_b,
        "abstention_delta": abst_b - abst_a,
        "matrix": matrix,
        "flips": {
            "correct_to_wrong": matrix[ci][wi],
            "wrong_to_correct": matrix[wi][ci],
            "correct_to_abstained": matrix[ci][ai],
            "abstained_to_correct": matrix[ai][ci],
            "wrong_to_abstained": matrix[wi][ai],
            "abstained_to_wrong": matrix[ai][wi],
            "total_flips": off_diag,
            "flip_rate": (off_diag / n_cmp) if n_cmp else 0.0,
            "net_correct_change": counts_b["correct"] - counts_a["correct"],
        },
        "diffs": diffs,
    }


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def _fmt_matrix(matrix: list[list[int]]) -> list[str]:
    lines = ["| A \\ B | correct | wrong | abstained | (row sum) |",
             "| --- | --: | --: | --: | --: |"]
    for i, c in enumerate(CLASSES):
        row = matrix[i]
        lines.append(f"| **{c}** | {row[0]} | {row[1]} | {row[2]} | {sum(row)} |")
    col = [sum(matrix[r][j] for r in range(len(CLASSES))) for j in range(len(CLASSES))]
    lines.append(f"| **(col sum)** | {col[0]} | {col[1]} | {col[2]} | {sum(col)} |")
    return lines


def build_report(base_a: str, base_b: str, results: dict[str, dict],
                 missing_a: list[str], missing_b: list[str]) -> str:
    L: list[str] = []
    W = L.append
    today = date.today().strftime("%Y-%m-%d")
    W("# Cobbie factorial run comparison")
    W("")
    W(f"Generated {today}.")
    W(f"- A (reference): `{base_a}`")
    W(f"- B (compared):  `{base_b}`")
    W("")
    W("Comparable set per cell = question ids present in BOTH cells whose "
      "classification is correct/wrong/abstained on BOTH sides. NULL/unjudged "
      "and error rows are excluded (reported as dropped, never counted as wrong). "
      "accuracy = correct / n_comparable.")
    W("")
    if missing_a:
        W(f"WARNING: cells present in B but missing in A: {', '.join(f'`{c}`' for c in missing_a)}")
    if missing_b:
        W(f"WARNING: cells present in A but missing in B: {', '.join(f'`{c}`' for c in missing_b)}")
    if missing_a or missing_b:
        W("")

    if not results:
        W("No common cells with results.sqlite found in both bases.")
        return "\n".join(L) + "\n"

    # --- per-cell summary table ------------------------------------------- #
    W("## Per-cell summary")
    W("")
    W("| cell | n_A | n_B | n_∩ | drop_unjudged | drop_error | n_cmp | acc_A | acc_B | Δacc | abst_A | abst_B | Δabst | flips | flip_rate | net_correct |")
    W("| --- | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: | --: |")
    for cell, r in results.items():
        f = r["flips"]
        W(
            f"| `{cell}` | {r['n_A']} | {r['n_B']} | {r['n_intersection']} | "
            f"{r['dropped_unjudged']} | {r['dropped_error']} | {r['n_comparable']} | "
            f"{r['accuracy_A']:.3f} | {r['accuracy_B']:.3f} | {r['accuracy_delta']:+.3f} | "
            f"{r['abstention_A']:.3f} | {r['abstention_B']:.3f} | {r['abstention_delta']:+.3f} | "
            f"{f['total_flips']} | {f['flip_rate']:.3f} | {f['net_correct_change']:+d} |"
        )
    W("")

    # --- per-cell detail -------------------------------------------------- #
    for cell, r in results.items():
        f = r["flips"]
        W(f"## `{cell}`")
        W("")
        W(f"- rows: A={r['n_A']}, B={r['n_B']}, intersection={r['n_intersection']}, "
          f"comparable={r['n_comparable']} "
          f"(dropped: unjudged/NULL={r['dropped_unjudged']}, error={r['dropped_error']})")
        ca, cb = r["counts_A"], r["counts_B"]
        W(f"- A breakdown (comparable): correct={ca['correct']}, wrong={ca['wrong']}, "
          f"abstained={ca['abstained']}")
        W(f"- B breakdown (comparable): correct={cb['correct']}, wrong={cb['wrong']}, "
          f"abstained={cb['abstained']}")
        W(f"- accuracy: A={r['accuracy_A']:.3f}, B={r['accuracy_B']:.3f}, "
          f"Δ={r['accuracy_delta']:+.3f}")
        W(f"- abstention rate: A={r['abstention_A']:.3f}, B={r['abstention_B']:.3f}, "
          f"Δ={r['abstention_delta']:+.3f}")
        W("")
        W("Flip headlines (A→B):")
        W(f"- correct→wrong (regressions): {f['correct_to_wrong']}")
        W(f"- wrong→correct (gains): {f['wrong_to_correct']}")
        W(f"- abstained→correct: {f['abstained_to_correct']}")
        W(f"- correct→abstained: {f['correct_to_abstained']}")
        W(f"- net correct change: {f['net_correct_change']:+d}")
        W(f"- total flips: {f['total_flips']} (flip rate {f['flip_rate']:.3f})")
        W("")
        W("Transition matrix (counts, rows = A class, cols = B class):")
        W("")
        L.extend(_fmt_matrix(r["matrix"]))
        W("")

    # --- overall roll-up -------------------------------------------------- #
    W("## Overall roll-up (across compared cells)")
    W("")
    tot_cmp = sum(r["n_comparable"] for r in results.values())
    tot_flips = sum(r["flips"]["total_flips"] for r in results.values())
    tot_c2w = sum(r["flips"]["correct_to_wrong"] for r in results.values())
    tot_w2c = sum(r["flips"]["wrong_to_correct"] for r in results.values())
    tot_net = sum(r["flips"]["net_correct_change"] for r in results.values())
    tot_corr_a = sum(r["counts_A"]["correct"] for r in results.values())
    tot_corr_b = sum(r["counts_B"]["correct"] for r in results.values())
    macro_dacc = (
        sum(r["accuracy_delta"] for r in results.values()) / len(results)
    )
    micro_acc_a = tot_corr_a / tot_cmp if tot_cmp else 0.0
    micro_acc_b = tot_corr_b / tot_cmp if tot_cmp else 0.0
    W(f"- cells compared: {len(results)}")
    W(f"- total comparable questions: {tot_cmp}")
    W(f"- micro accuracy: A={micro_acc_a:.3f}, B={micro_acc_b:.3f}, "
      f"Δ={micro_acc_b - micro_acc_a:+.3f}")
    W(f"- macro mean Δaccuracy (cell-averaged): {macro_dacc:+.3f}")
    W(f"- total flips: {tot_flips} (overall flip rate "
      f"{(tot_flips / tot_cmp) if tot_cmp else 0.0:.3f})")
    W(f"- regressions (correct→wrong): {tot_c2w}; gains (wrong→correct): {tot_w2c}")
    W(f"- total net correct change: {tot_net:+d}")
    W("")
    return "\n".join(L) + "\n"


def write_csv(path: str, results: dict[str, dict]) -> int:
    rows = 0
    with open(path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            ["question_id", "cell", "class_A", "class_B", "predicted_A", "predicted_B"]
        )
        for cell, r in results.items():
            for d in r["diffs"]:
                writer.writerow(
                    [d["question_id"], cell, d["class_A"], d["class_B"],
                     d["predicted_A"], d["predicted_B"]]
                )
                rows += 1
    return rows


# --------------------------------------------------------------------------- #
# Self-test (env-guarded, no DBs needed)
# --------------------------------------------------------------------------- #
def _self_test() -> int:
    def mk(labels):
        return {qid: {"label": lab, "predicted": f"pred-{qid}"} for qid, lab in labels.items()}

    # A vs B with known flips + excluded rows.
    a = mk({
        1: "correct", 2: "correct", 3: "wrong", 4: "wrong",
        5: "abstained", 6: "abstained", 7: "correct",
        8: "unjudged", 9: "error", 10: "correct",  # 10 only in A
    })
    b = mk({
        1: "correct",    # stay
        2: "wrong",      # correct->wrong
        3: "correct",    # wrong->correct
        4: "wrong",      # stay
        5: "correct",    # abstained->correct
        6: "abstained",  # stay
        7: "abstained",  # correct->abstained
        8: "correct",    # excluded (A unjudged)
        9: "correct",    # excluded (A error)
        11: "correct",   # only in B
    })
    r = compare_cell(a, b)
    m = r["matrix"]

    assert r["n_A"] == 10 and r["n_B"] == 10, r
    assert r["n_intersection"] == 9, r  # ids 1-9 shared
    assert r["dropped_unjudged"] == 1, r  # qid 8
    assert r["dropped_error"] == 1, r     # qid 9
    assert r["n_comparable"] == 7, r      # qids 1-7

    # Row sums == per-class A counts; col sums == per-class B counts.
    for i, c in enumerate(CLASSES):
        assert sum(m[i]) == r["counts_A"][c], (c, m, r["counts_A"])
    for j, c in enumerate(CLASSES):
        assert sum(m[i][j] for i in range(3)) == r["counts_B"][c], (c, m, r["counts_B"])

    # Total flips == off-diagonal sum.
    off = sum(m[i][j] for i in range(3) for j in range(3) if i != j)
    assert r["flips"]["total_flips"] == off, r
    # Grand total of the matrix == n_comparable.
    assert sum(sum(row) for row in m) == r["n_comparable"], r

    f = r["flips"]
    assert f["correct_to_wrong"] == 1, f   # qid 2
    assert f["wrong_to_correct"] == 1, f   # qid 3
    assert f["abstained_to_correct"] == 1, f  # qid 5
    assert f["correct_to_abstained"] == 1, f  # qid 7
    assert f["total_flips"] == 4, f
    assert abs(f["flip_rate"] - 4 / 7) < 1e-9, f
    # net_correct change: A correct over comparable = {1,2,7}=3; B correct = {1,3,5}=3 -> 0
    assert f["net_correct_change"] == 0, f
    assert len(r["diffs"]) == 4, r["diffs"]

    # Identity comparison: zero flips, zero delta, no diffs.
    r2 = compare_cell(a, a)
    assert r2["accuracy_delta"] == 0.0, r2
    assert r2["flips"]["total_flips"] == 0, r2
    assert r2["flips"]["flip_rate"] == 0.0, r2
    assert r2["diffs"] == [], r2
    # Excluded rows (8 unjudged, 9 error) still dropped even in self-compare.
    assert r2["dropped_unjudged"] == 1 and r2["dropped_error"] == 1, r2

    print("compare_runs self-test: OK")
    return 0


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    if os.environ.get("COMPARE_RUNS_SELFTEST") == "1":
        return _self_test()

    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base_a", help="reference run dir (A side, e.g. outputs/factorial)")
    ap.add_argument("base_b", help="compared run dir (B side, e.g. a rerun)")
    ap.add_argument("--cells", nargs="+", default=None,
                    help="explicit cell names; default = intersection of both bases")
    ap.add_argument("--out", default=None, help="markdown report path")
    ap.add_argument("--csv", default=None, help="per-question changes CSV path")
    args = ap.parse_args()

    base_a = os.path.abspath(args.base_a)
    base_b = os.path.abspath(args.base_b)
    for b in (base_a, base_b):
        if not os.path.isdir(b):
            print(f"ERROR: {b} is not a directory", file=sys.stderr)
            return 2

    cells_a = discover_cells(base_a)
    cells_b = discover_cells(base_b)
    set_a, set_b = set(cells_a), set(cells_b)

    if args.cells:
        requested = list(dict.fromkeys(args.cells))  # de-dupe, keep order
        cells = [c for c in requested if c in set_a and c in set_b]
        skipped = [c for c in requested if c not in set_a or c not in set_b]
        for c in skipped:
            where = []
            if c not in set_a:
                where.append("A")
            if c not in set_b:
                where.append("B")
            print(f"WARNING: requested cell `{c}` missing in {','.join(where)}; skipped",
                  file=sys.stderr)
    else:
        cells = sorted(set_a & set_b)

    missing_a = sorted(set_b - set_a)  # in B, not in A
    missing_b = sorted(set_a - set_b)  # in A, not in B

    if not cells:
        print("ERROR: no common cells (with results.sqlite) to compare", file=sys.stderr)
        if missing_a:
            print(f"  only in B: {missing_a}", file=sys.stderr)
        if missing_b:
            print(f"  only in A: {missing_b}", file=sys.stderr)
        return 2

    results: dict[str, dict] = {}
    for cell in cells:
        a = load_cell(base_a, cell)
        b = load_cell(base_b, cell)
        results[cell] = compare_cell(a, b)

    report = build_report(base_a, base_b, results, missing_a, missing_b)

    if args.out:
        out_path = os.path.abspath(args.out)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as fh:
            fh.write(report)
        print(f"Report written to: {out_path}")

    csv_rows = None
    if args.csv:
        csv_path = os.path.abspath(args.csv)
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        csv_rows = write_csv(csv_path, results)
        print(f"Changes CSV written to: {csv_path} ({csv_rows} changed questions)")

    # Always echo a concise summary to stdout.
    print()
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
