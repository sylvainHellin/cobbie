"""Consolidate a two-coder open-coding run into a candidate codebook.

Reads the minimax and claude coder outputs produced for an open-coding run and
produces (a) a human-readable report and (b) a machine-readable join, to drive
stage-2 controlled-vocabulary consolidation.

For each assembled prompt ``<rundir>/{orig,rerun_divergent}/<stem>.md`` two
coders write ``<stem>.minimax.json`` and ``<stem>.claude.json``. Each JSON may
be wrapped in a ```json ... ``` markdown fence (stripped before parsing; if
``json.loads`` still fails we fall back to slicing from the first ``{`` to the
last ``}``). The schema each coder emits:

    {question_id:int, verdict:'correct'|'wrong'|'abstained',
     mechanisms:[{label,evidence,note}], errors:[{label,evidence,note}],
     primary_factor:str, notes:str}

The ``.md`` filename stem encodes the judge's ground-truth verdict, e.g.
``q169_r0_correct`` -> ``correct``.

This script:
  1. Globs both coders' JSON recursively and defensively parses each (every
     parse failure recorded with path + first 200 chars).
  2. Keys results by relative stem (dir + base without the coder suffix) so
     ``orig`` vs ``rerun_divergent`` with the same qid stay distinct, and joins
     the two coders per stem.
  3. Sanity-checks each coder's reported verdict against the filename verdict
     (catches coder drift).
  4. Computes inter-coder verdict agreement (stems where both present) plus a
     verdict confusion matrix (minimax x claude).
  5. Flattens mechanisms[].label / errors[].label / primary_factor into
     normalised (strip+lower) frequency tables, kept separate per field and per
     coder.
  6. Writes ``_consolidation_report.md`` and ``_consolidation_records.json`` in
     the run dir.

Runs incrementally on whatever subset is present and re-runs cleanly as more
land.

Usage:
    uv run python scripts/consolidate_opencoding.py
    uv run python scripts/consolidate_opencoding.py \
        --run-dir outputs/analysis/opencoding_full_20260626 --top 40
"""

import argparse
import glob
import json
import os
from collections import Counter, defaultdict

DEFAULT_RUN_DIR = "outputs/analysis/opencoding_full_20260626"
VERDICTS = ("correct", "wrong", "abstained")
CODERS = ("minimax", "claude")


def parse_coder_json(text):
    """Parse a coder JSON payload, tolerating ```json fences and prose wrap.

    Returns (obj, error). On success error is None; on failure obj is None and
    error is a short reason string.
    """
    raw = text.strip()
    if not raw:
        return None, "empty file"
    body = raw
    # strip a leading ```json / ``` fence and trailing ``` if present
    if body.startswith("```"):
        first_nl = body.find("\n")
        if first_nl != -1:
            body = body[first_nl + 1 :]
        if body.rstrip().endswith("```"):
            body = body.rstrip()[: -len("```")]
    body = body.strip()
    try:
        obj = json.loads(body)
    except json.JSONDecodeError:
        start = body.find("{")
        end = body.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None, "no JSON object found"
        try:
            obj = json.loads(body[start : end + 1])
        except json.JSONDecodeError as exc:
            return None, "JSONDecodeError: " + str(exc)
    if not isinstance(obj, dict):
        return None, "parsed value is not an object (%s)" % type(obj).__name__
    return obj, None


def filename_verdict(stem):
    """Ground-truth verdict encoded in the stem, e.g. q169_r0_correct."""
    base = os.path.basename(stem)
    tail = base.rsplit("_", 1)[-1].lower()
    return tail if tail in VERDICTS else None


def labels_from(obj, field):
    """Normalised label strings from a mechanisms/errors list field."""
    out = []
    items = obj.get(field)
    if not isinstance(items, list):
        return out
    for item in items:
        if isinstance(item, dict):
            label = item.get("label")
        elif isinstance(item, str):
            label = item
        else:
            label = None
        if isinstance(label, str) and label.strip():
            out.append(label.strip().lower())
    return out


def collect(run_dir):
    """Glob + parse both coders. Returns (records, parse_failures)."""
    records = {}
    parse_failures = []
    for coder in CODERS:
        pattern = os.path.join(run_dir, "**", "*.%s.json" % coder)
        for path in sorted(glob.glob(pattern, recursive=True)):
            rel = os.path.relpath(path, run_dir)
            stem = rel[: -len(".%s.json" % coder)]
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
            obj, err = parse_coder_json(text)
            rec = records.setdefault(
                stem,
                {
                    "stem": stem,
                    "filename_verdict": filename_verdict(stem),
                    "minimax": None,
                    "claude": None,
                },
            )
            if err is not None:
                parse_failures.append(
                    {"path": rel, "coder": coder, "error": err, "head": text[:200]}
                )
                continue
            rec[coder] = obj
    return records, parse_failures


def reported_verdict(obj):
    if isinstance(obj, dict):
        v = obj.get("verdict")
        if isinstance(v, str):
            return v.strip().lower()
    return None


def build_summary(records, parse_failures, top):
    coded = {c: 0 for c in CODERS}
    verdict_mismatch = []  # coder reported verdict != filename verdict
    both_present = 0
    verdict_agree = 0
    confusion = defaultdict(int)  # (minimax_verdict, claude_verdict) -> n
    label_counts = {
        c: {"mechanisms": Counter(), "errors": Counter(), "primary_factor": Counter()}
        for c in CODERS
    }

    for stem, rec in records.items():
        fv = rec["filename_verdict"]
        for c in CODERS:
            obj = rec[c]
            if obj is None:
                continue
            coded[c] += 1
            rv = reported_verdict(obj)
            if rv is not None and fv is not None and rv != fv:
                verdict_mismatch.append(
                    {"stem": stem, "coder": c, "reported": rv, "filename": fv}
                )
            for field in ("mechanisms", "errors"):
                label_counts[c][field].update(labels_from(obj, field))
            pf = obj.get("primary_factor")
            if isinstance(pf, str) and pf.strip():
                label_counts[c]["primary_factor"][pf.strip().lower()] += 1

        mo, co = rec["minimax"], rec["claude"]
        if mo is not None and co is not None:
            both_present += 1
            mv, cv = reported_verdict(mo), reported_verdict(co)
            confusion[(mv, cv)] += 1
            if mv is not None and cv is not None and mv == cv:
                verdict_agree += 1

    return {
        "n_stems": len(records),
        "coded": coded,
        "parse_failures": parse_failures,
        "verdict_mismatch": verdict_mismatch,
        "both_present": both_present,
        "verdict_agree": verdict_agree,
        "confusion": confusion,
        "label_counts": label_counts,
        "top": top,
    }


def _fmt_table(counter, top):
    if not counter:
        return "  (none yet)\n"
    lines = []
    for label, n in counter.most_common(top):
        lines.append("  %4d  %s" % (n, label))
    return "\n".join(lines) + "\n"


def render_report(summary):
    s = summary
    top = s["top"]
    out = []
    out.append("# Open-coding consolidation report\n")
    out.append(
        "Stems seen: %d  |  minimax coded: %d  |  claude coded: %d  |  both: %d\n"
        % (s["n_stems"], s["coded"]["minimax"], s["coded"]["claude"], s["both_present"])
    )

    # inter-coder verdict agreement
    bp = s["both_present"]
    if bp:
        pct = 100.0 * s["verdict_agree"] / bp
        out.append(
            "\n## Inter-coder verdict agreement\n%d/%d = %.1f%% (stems where both coders present)\n"
            % (s["verdict_agree"], bp, pct)
        )
        out.append("\nConfusion (rows=minimax, cols=claude):\n")
        header = "minimax\\claude  " + "  ".join("%-9s" % (v or "?") for v in VERDICTS)
        out.append(header + "\n")
        for mv in VERDICTS:
            cells = []
            for cv in VERDICTS:
                cells.append("%-9d" % s["confusion"].get((mv, cv), 0))
            out.append("%-15s %s\n" % (mv, "  ".join(cells)))
        # any verdicts outside the canonical set
        odd = {k: v for k, v in s["confusion"].items() if not (set(k) <= set(VERDICTS))}
        if odd:
            out.append("Non-canonical verdict pairs: %s\n" % dict(odd))
    else:
        out.append("\n## Inter-coder verdict agreement\n(no stem coded by both yet)\n")

    # verdict vs filename mismatches (coder drift)
    out.append(
        "\n## Reported-verdict vs filename mismatches: %d\n" % len(s["verdict_mismatch"])
    )
    for m in s["verdict_mismatch"][:50]:
        out.append(
            "  %s [%s] reported=%s filename=%s\n"
            % (m["stem"], m["coder"], m["reported"], m["filename"])
        )

    # parse failures
    out.append("\n## Parse failures: %d\n" % len(s["parse_failures"]))
    for f in s["parse_failures"][:50]:
        out.append(
            "  %s [%s] %s | %s\n"
            % (f["path"], f["coder"], f["error"], f["head"].replace("\n", " ")[:120])
        )

    # vocabulary tables
    for c in CODERS:
        out.append("\n## %s candidate vocabulary\n" % c)
        out.append("\n### mechanisms (top %d)\n" % top)
        out.append(_fmt_table(s["label_counts"][c]["mechanisms"], top))
        out.append("\n### errors (top %d)\n" % top)
        out.append(_fmt_table(s["label_counts"][c]["errors"], top))
        out.append("\n### primary_factor (top %d)\n" % top)
        out.append(_fmt_table(s["label_counts"][c]["primary_factor"], top))

    return "".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run-dir", default=DEFAULT_RUN_DIR)
    ap.add_argument(
        "--top", type=int, default=40, help="rows per vocabulary table (default 40)"
    )
    args = ap.parse_args()

    records, parse_failures = collect(args.run_dir)
    summary = build_summary(records, parse_failures, args.top)
    report = render_report(summary)

    report_path = os.path.join(args.run_dir, "_consolidation_report.md")
    records_path = os.path.join(args.run_dir, "_consolidation_records.json")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write(report)
    with open(records_path, "w", encoding="utf-8") as fh:
        json.dump(
            {"records": records, "parse_failures": parse_failures},
            fh,
            ensure_ascii=False,
            indent=2,
        )

    print(report)
    print("\nwrote %s" % report_path)
    print("wrote %s" % records_path)


if __name__ == "__main__":
    main()
