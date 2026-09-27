# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Stage 3 of the closed-coding pipeline: turn the Stage-2 census codings into
the paper's RQ2 (mechanisms) / RQ3 (errors) numbers.

PURE, deterministic, NO LLM calls, all inputs opened READ-ONLY. The only writes
land under ``<census-dir>/analysis/``. Never pools ``orig`` and
``rerun_divergent`` -- every table is per-set (and per-coder / pooled), and the
two sets live in structurally separate output subdirs.

What it computes, per set, per coder (glm-5.2, minimax-m3 = the two independent
coders) and pooled (2x denominator):

  * Mechanisms (RQ2): per-M prevalence over non-stub traces; the
    schema-structure-discovery UMBRELLA UNION (M1 v M2 v M3 v M4) plus each
    sub-code; conditional accuracy P(correct|m); a necessity/lift read
    (P(m|correct) vs P(m|wrong)); every ratio shows its denominator.
  * Errors (RQ3): distribution over wrong+abstained; agent-track vs
    non-agent/exogenous split FROM the frozen ``track`` field; share of NC
    traces whose error set is solely exogenous.
  * Layered honest error rate -- three peels. Decision (a): the chain runs on
    the WRONG-ONLY base by default (``--nc-basis``); abstained is a DISTINCT
    outcome, reported as its own category (with E14/E7 breakdown), not an error.
    (a) raw (both wrong-only and wrong+abstained shown); (b) system-attributable
    (peel a trace only when error_ids subset of {E7,E14}; MIXED agent+exogenous
    KEPT); (c) core-capability (peel transparency-only, judge-derived).
  * Judge-criterion decomposition: per-criterion No counts + transparency-only
    (f=c=r=Yes AND t=No, guarding Na) read straight off the set's results.sqlite
    (read-only; never re-derived).
  * Flip sub-study (rerun_divergent): 1:1 by question_id. Decision (b): the
    contrast is CORRECT-path vs NON-CORRECT-path (non-correct = wrong u
    abstained), folding abstention in -> 71 contrast pairs (66 correct<->wrong +
    5 correct<->abstained): errors on the non-correct path + mechanisms unique to
    the correct path. The 9 wrong<->abstained pairs have no correct path and are
    reported separately (failure-mode divergence).
  * Two-coder IRR: per-code Cohen's kappa + per-trace Jaccard + exact-set-match,
    mechanisms and errors, per set.
  * A seeded, stratified-by-(set,verdict) human sanity-check dump.

Stubs = any coding object carrying an ``_error`` key; excluded from every
numerator/denominator, counted separately, reconciled against
``_state.json:flagged``. Taxonomy + track + umbrella are always loaded from the
frozen JSON, never hard-coded. If a denominator is 0 (e.g. rerun_divergent
codings not yet produced) the table emits an explicit ``pending_census`` marker
instead of dividing by zero.

Usage:
    uv run python scripts/analyze_census.py            # --set all, auto-detect coders
    uv run python scripts/analyze_census.py --set orig
    uv run python scripts/analyze_census.py --self-test   # unit fixtures, no writes
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_THIS_DIR)
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

# Reuse read-only sqlite + trace helpers (never reinvent, never lock the writer).
import build_trace_history as bth  # noqa: E402  (_connect_ro, load_result_row)
import build_review_sample as brs  # noqa: E402  (stratified_sample, read_trace_text)

SETS = ("orig", "rerun_divergent")
VERDICTS = ("correct", "wrong", "abstained")
NC_VERDICTS = ("wrong", "abstained")
# Pooled = N-coder sum of per-(coder,trace) observations: 2x denominator when both
# coders coded a trace, 1x when only one coder is present (under --coders auto-detect).
POOLED_LABEL = "pooled (N-coder ∑: 2× both present / 1× if one)"
_TID_RE = re.compile(r"q(\d+)_r(\d+)_(\w+)")

DEFAULTS = {
    "census_dir": "outputs/analysis/census_20260701",
    "records": "outputs/analysis/opencoding_full_20260626/_consolidation_records.json",
    "mechanisms": "outputs/analysis/opencoding_full_20260626/codebook/mechanisms.frozen.json",
    "errors": "outputs/analysis/opencoding_full_20260626/codebook/errors.frozen.json",
    "orig_db": "outputs/factorial/minimax-m3__agentic__none/results.sqlite",
    "rerun_db": "outputs/factorial_rerun_20260624/minimax-m3__agentic__none/results.sqlite",
    "trace_dir": "outputs/analysis/opencoding_full_20260626",
}


# --------------------------------------------------------------------------- #
# Loaders (all read-only)
# --------------------------------------------------------------------------- #
def load_vocab(mech_path: str, err_path: str) -> dict:
    """id -> {name, umbrella, track} for mechanisms + errors, from frozen JSON.

    Never hard-code the taxonomy: the umbrella (schema-structure-discovery) and
    the agent/non-agent track split are read straight off the frozen file.
    """
    with open(mech_path, encoding="utf-8") as f:
        mech_raw = json.load(f)
    with open(err_path, encoding="utf-8") as f:
        err_raw = json.load(f)

    mech = {}
    mech_order = []
    umbrella = defaultdict(list)
    for c in mech_raw["categories"]:
        mech[c["id"]] = {"name": c["name"], "umbrella": c.get("umbrella"),
                         "track": c.get("track")}
        mech_order.append(c["id"])
        if c.get("umbrella"):
            umbrella[c["umbrella"]].append(c["id"])

    err = {}
    err_order = []
    agent_ids, non_agent_ids = [], []
    for c in err_raw["categories"]:
        track = c.get("track")
        err[c["id"]] = {"name": c["name"], "track": track}
        err_order.append(c["id"])
        if track == "agent":
            agent_ids.append(c["id"])
        elif track == "non-agent":
            non_agent_ids.append(c["id"])

    return {
        "mech": mech,
        "mech_order": mech_order,
        "umbrella": dict(umbrella),
        "err": err,
        "err_order": err_order,
        "agent_ids": set(agent_ids),
        "non_agent_ids": set(non_agent_ids),
    }


def load_records(records_path: str) -> dict:
    """Per-set list + qid-keyed maps for flip pairing (records = authoritative
    filename verdicts)."""
    with open(records_path, encoding="utf-8") as f:
        recs = json.load(f)
    by_set = defaultdict(list)
    for r in recs:
        by_set[r["set"]].append(r)
    orig_by_qid = {r["question_id"]: r for r in by_set.get("orig", [])}
    rd_by_qid = {r["question_id"]: r for r in by_set.get("rerun_divergent", [])}
    return {"all": recs, "by_set": dict(by_set),
            "orig_by_qid": orig_by_qid, "rd_by_qid": rd_by_qid}


def is_stub(obj: dict) -> bool:
    return isinstance(obj, dict) and "_error" in obj


def load_codings(census_dir: str, slug: str, sset: str):
    """Return (valid_dict, stub_dict) or None when the file is absent (set not
    coded yet). A coding is a stub iff it carries an ``_error`` key."""
    path = os.path.join(census_dir, slug, f"{sset}.codings.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    valid, stubs = {}, {}
    for k, v in d.items():
        (stubs if is_stub(v) else valid)[k] = v
    return valid, stubs


def load_state_flagged(census_dir: str, slug: str, sset: str):
    path = os.path.join(census_dir, slug, "_state.json")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        st = json.load(f)
    return st.get("sets", {}).get(sset, {}).get("flagged")


_JUDGE_CACHE: dict[str, dict] = {}


def load_judge(db_path: str) -> dict:
    """(question_id, repeat_idx) -> criterion row, via read-only _connect_ro."""
    if db_path in _JUDGE_CACHE:
        return _JUDGE_CACHE[db_path]
    conn = bth._connect_ro(db_path)
    try:
        rows = conn.execute(
            "SELECT question_id, repeat_idx, classification, abstention, "
            "faithfulness, completeness, transparency, relevance, justification "
            "FROM results"
        ).fetchall()
    finally:
        conn.close()
    idx = {(r["question_id"], r["repeat_idx"]): dict(r) for r in rows}
    _JUDGE_CACHE[db_path] = idx
    return idx


def parse_tid(tid: str):
    m = _TID_RE.match(tid)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), m.group(3)


def verdict_of(obj: dict) -> str:
    return obj.get("verdict")


# --------------------------------------------------------------------------- #
# Raw counters (pool-able by summation) + reports
# --------------------------------------------------------------------------- #
def mech_raw(valid: dict, vocab: dict) -> dict:
    """Per-mechanism present/correct/wrong counts + umbrella-union counts."""
    schema_ids = set(vocab["umbrella"].get("schema-structure-discovery", []))
    codes = {m: {"present": 0, "correct_present": 0, "wrong_present": 0}
             for m in vocab["mech_order"]}
    n = n_correct = n_wrong = 0
    uu = {"present": 0, "correct_present": 0}
    for obj in valid.values():
        n += 1
        v = verdict_of(obj)
        if v == "correct":
            n_correct += 1
        elif v == "wrong":
            n_wrong += 1
        ids = set(obj.get("mechanism_ids") or [])
        for m in ids:
            if m not in codes:  # unknown id -> track defensively
                codes[m] = {"present": 0, "correct_present": 0, "wrong_present": 0}
            codes[m]["present"] += 1
            if v == "correct":
                codes[m]["correct_present"] += 1
            elif v == "wrong":
                codes[m]["wrong_present"] += 1
        if ids & schema_ids:
            uu["present"] += 1
            if v == "correct":
                uu["correct_present"] += 1
    return {"n": n, "n_correct": n_correct, "n_wrong": n_wrong,
            "codes": codes, "umbrella_union": uu,
            "schema_ids": sorted(schema_ids)}


def _ratio(num, den):
    return None if not den else num / den


def mech_report(raw: dict, vocab: dict) -> dict:
    n = raw["n"]
    if n == 0:
        return {"status": "pending_census", "n_traces": 0}
    baseline = _ratio(raw["n_correct"], n)
    out = {"n_traces": n, "n_correct": raw["n_correct"], "n_wrong": raw["n_wrong"],
           "baseline_p_correct": baseline, "mechanisms": {}}
    for m, c in raw["codes"].items():
        present = c["present"]
        cond_acc = _ratio(c["correct_present"], present)
        out["mechanisms"][m] = {
            "name": vocab["mech"].get(m, {}).get("name", m),
            "umbrella": vocab["mech"].get(m, {}).get("umbrella"),
            "present": present,
            "prevalence": _ratio(present, n),
            "denominator": n,
            "conditional_accuracy_p_correct_given_m": cond_acc,
            "cond_acc_denominator": present,
            "lift_vs_baseline": (cond_acc / baseline)
            if (cond_acc is not None and baseline) else None,
            "p_m_given_correct": _ratio(c["correct_present"], raw["n_correct"]),
            "p_m_given_wrong": _ratio(c["wrong_present"], raw["n_wrong"]),
            "necessity_diff_correct_minus_wrong": (
                (_ratio(c["correct_present"], raw["n_correct"]) or 0)
                - (_ratio(c["wrong_present"], raw["n_wrong"]) or 0)
            ) if (raw["n_correct"] and raw["n_wrong"]) else None,
        }
    uu = raw["umbrella_union"]
    out["schema_umbrella_union"] = {
        "member_ids": raw["schema_ids"],
        "present": uu["present"],
        "prevalence": _ratio(uu["present"], n),
        "denominator": n,
        "conditional_accuracy_p_correct_given_union": _ratio(
            uu["correct_present"], uu["present"]),
    }
    return out


def err_raw(valid: dict, vocab: dict) -> dict:
    """Per-error counts over NC = wrong u abstained, + exogenous/empty bookkeeping."""
    agent_ids, non_agent_ids = vocab["agent_ids"], vocab["non_agent_ids"]
    codes = {e: 0 for e in vocab["err_order"]}
    n_nc = 0
    n_solely_exo = 0
    n_empty = 0
    solely_exo_ids = []
    empty_ids = []
    for tid, obj in valid.items():
        if verdict_of(obj) not in NC_VERDICTS:
            continue
        n_nc += 1
        ids = set(obj.get("error_ids") or [])
        for e in ids:
            codes[e] = codes.get(e, 0) + 1
        if not ids:
            n_empty += 1
            empty_ids.append(tid)
        elif ids <= non_agent_ids:
            n_solely_exo += 1
            solely_exo_ids.append(tid)
    return {"n_nc": n_nc, "codes": codes,
            "n_solely_exogenous": n_solely_exo, "solely_exo_ids": solely_exo_ids,
            "n_empty_error_set": n_empty, "empty_ids": empty_ids}


def err_report(raw: dict, vocab: dict) -> dict:
    n = raw["n_nc"]
    if n == 0:
        return {"status": "pending_census", "n_nc": 0}
    agent_block, non_agent_block = {}, {}
    for e, cnt in raw["codes"].items():
        track = vocab["err"].get(e, {}).get("track")
        entry = {"name": vocab["err"].get(e, {}).get("name", e),
                 "present": cnt, "prevalence": _ratio(cnt, n), "denominator": n}
        (agent_block if track == "agent" else non_agent_block)[e] = entry
    return {
        "n_nc": n,
        "agent_track": agent_block,
        "non_agent_track": non_agent_block,
        "n_solely_exogenous": raw["n_solely_exogenous"],
        "share_solely_exogenous": _ratio(raw["n_solely_exogenous"], n),
        "n_empty_error_set": raw["n_empty_error_set"],
        "share_empty_error_set": _ratio(raw["n_empty_error_set"], n),
        "empty_error_set_ids": raw["empty_ids"],
    }


def transparency_only(judge: dict, tid: str) -> bool:
    """f=c=r=Yes AND t=No. Guards Na: abstained rows are all-'Na' -> never True."""
    p = parse_tid(tid)
    if p is None:
        return False
    row = judge.get((p[0], p[1]))
    if not row:
        return False
    return (row.get("faithfulness") == "Yes" and row.get("completeness") == "Yes"
            and row.get("relevance") == "Yes" and row.get("transparency") == "No")


def honest_raw(valid: dict, judge: dict, vocab: dict, nc_basis: str = "wrong-only") -> dict:
    """Peels (a)(b)(c) as raw counts. n_all = all non-stub traces (the base T).

    Decision (a): the peel CHAIN runs over the ``nc_basis`` surface -- default
    ``wrong-only`` (abstained is a DISTINCT outcome, not an error, reported
    separately below), or ``wrong-plus-abstained`` to fold abstained back in.
    Peel (a) always reports BOTH raw figures regardless of basis.
    """
    non_agent_ids = vocab["non_agent_ids"]
    n_all = len(valid)
    basis_verdicts = ("wrong",) if nc_basis == "wrong-only" else ("wrong", "abstained")
    n_wrong = n_abstained = n_nc = n_purely_exo = n_empty = 0
    # abstained composition (reported as its own outcome under decision (a))
    abst_e14 = abst_e7 = abst_purely_exo = abst_empty = 0
    sys_ids, pres_ids = [], []
    for tid, obj in valid.items():
        v = verdict_of(obj)
        if v == "wrong":
            n_wrong += 1
        elif v == "abstained":
            n_abstained += 1
            a_ids = set(obj.get("error_ids") or [])
            if "E14" in a_ids:
                abst_e14 += 1
            if "E7" in a_ids:
                abst_e7 += 1
            if not a_ids:
                abst_empty += 1
            elif a_ids <= non_agent_ids:
                abst_purely_exo += 1
        if v in ("wrong", "abstained"):
            n_nc += 1
        if v not in basis_verdicts:
            continue
        ids = set(obj.get("error_ids") or [])
        if not ids:
            n_empty += 1
            in_sys = True  # empty = coder gap: kept in SYS but flagged (Q4)
        elif ids <= non_agent_ids:
            n_purely_exo += 1
            in_sys = False  # purely exogenous -> peeled at (b)
        else:
            in_sys = True  # >=1 agent error (incl. mixed agent+exogenous) -> kept
        if in_sys:
            sys_ids.append(tid)
            if transparency_only(judge, tid):
                pres_ids.append(tid)
    return {"n_all": n_all, "nc_basis": nc_basis,
            "n_wrong": n_wrong, "n_abstained": n_abstained, "n_nc": n_nc,
            "n_purely_exo": n_purely_exo, "n_empty": n_empty,
            "n_sys": len(sys_ids), "n_pres": len(pres_ids),
            "n_core": len(sys_ids) - len(pres_ids),
            "abst_e14": abst_e14, "abst_e7": abst_e7,
            "abst_purely_exo": abst_purely_exo, "abst_empty": abst_empty}


def honest_report(raw: dict) -> dict:
    n = raw["n_all"]
    if n == 0:
        return {"status": "pending_census", "n_traces": 0}
    basis = raw.get("nc_basis", "wrong-only")
    return {
        "n_traces": n,
        "nc_basis": basis,
        "peel_a_raw": {
            "chain_base": basis,
            "wrong_only": {"count": raw["n_wrong"], "rate": _ratio(raw["n_wrong"], n)},
            "wrong_plus_abstained": {"count": raw["n_nc"], "rate": _ratio(raw["n_nc"], n)},
            "note": "Decision (a): the peel chain runs on the '" + basis + "' base; "
                    "abstained is a distinct outcome (see abstained_outcome), NOT an "
                    "error. Both raw figures shown.",
        },
        "abstained_outcome": {
            "count": raw["n_abstained"], "rate": _ratio(raw["n_abstained"], n),
            "n_with_E14_infra": raw["abst_e14"], "n_with_E7_judge": raw["abst_e7"],
            "n_purely_exogenous": raw["abst_purely_exo"],
            "n_empty_error_set": raw["abst_empty"],
            "note": "Reported as its own outcome category (decision a), NOT folded into "
                    "the error chain. E14-driven (infra) abstentions noted separately.",
        },
        "peel_b_system_attributable": {
            "count": raw["n_sys"], "rate": _ratio(raw["n_sys"], n),
            "n_purely_exogenous_peeled": raw["n_purely_exo"],
            "n_empty_error_set_kept_flagged": raw["n_empty"],
            "note": "kept iff >=1 agent-track error; mixed agent+exogenous KEPT; "
                    "empty-error-set NC traces KEPT and flagged (coder gap).",
        },
        "peel_c_core_capability": {
            "count": raw["n_core"], "rate": _ratio(raw["n_core"], n),
            "n_transparency_only_peeled": raw["n_pres"],
            "note": "transparency-only (judge-derived: f=c=r=Yes & t=No) removed "
                    "from SYS; peel is judge-identical, rate is coder-specific via SYS. "
                    "DIFFERENT population from judge_decomp.transparency_only: this "
                    "peel is over the coder-specific SYS set; judge_decomp is over ALL "
                    "wrong records (coder-independent). Different denominators by design.",
        },
    }


def judge_decomp(records_for_set: list, judge: dict) -> dict:
    """Per-criterion No counts + transparency-only over the set's wrong records
    (judge-derived, coder-independent). Abstained handled separately (all-Na).

    NOTE: this transparency_only is a DIFFERENT population from the honest peel (c)
    n_transparency_only_peeled, which is over the coder-specific SYS set. This one
    ranges over ALL wrong records; different denominators by design -- do not conflate."""
    crits = ("faithfulness", "completeness", "transparency", "relevance")
    no_counts = {c: 0 for c in crits}
    n_wrong = n_abst = n_missing = 0
    n_transp_only = 0
    transp_ids = []
    for r in records_for_set:
        v = r["verdict"]
        row = judge.get((r["question_id"], 0))
        if row is None:
            n_missing += 1
            continue
        if v == "abstained":
            n_abst += 1
            continue
        if v == "wrong":
            n_wrong += 1
            for c in crits:
                if row.get(c) == "No":
                    no_counts[c] += 1
            if (row.get("faithfulness") == "Yes" and row.get("completeness") == "Yes"
                    and row.get("relevance") == "Yes" and row.get("transparency") == "No"):
                n_transp_only += 1
                transp_ids.append(r["trace_id"])
    if n_wrong == 0:
        return {"status": "pending_census_or_no_wrong", "n_wrong": 0,
                "n_abstained": n_abst, "n_missing_judge_row": n_missing}
    return {
        "n_wrong": n_wrong, "n_abstained_all_Na": n_abst,
        "n_missing_judge_row": n_missing,
        "no_counts_over_wrong": {c: {"count": no_counts[c],
                                     "share": _ratio(no_counts[c], n_wrong)}
                                 for c in crits},
        "transparency_only": {"count": n_transp_only,
                              "share_of_wrong": _ratio(n_transp_only, n_wrong),
                              "trace_ids": transp_ids,
                              "note": "f=c=r=Yes & t=No; Na-guarded (abstained never match)."},
    }


# --------------------------------------------------------------------------- #
# IRR (per set, mechanisms + errors)
# --------------------------------------------------------------------------- #
def cohen_kappa_binary(a: list, b: list):
    n = len(a)
    if n == 0:
        return None
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pa1, pb1 = sum(a) / n, sum(b) / n
    pe = pa1 * pb1 + (1 - pa1) * (1 - pb1)
    if pe >= 1.0:  # no variance in expectation (both constant) -> kappa undefined
        return None
    return (po - pe) / (1 - pe)


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return (sum(xs) / len(xs)) if xs else None


def irr_block(shared_tids: list, validA: dict, validB: dict, code_order: list,
              field: str) -> dict:
    """Per-code kappa + per-trace Jaccard + exact-set-match over shared traces."""
    n = len(shared_tids)
    if n == 0:
        return {"status": "pending_census", "n_shared": 0}
    per_code = {}
    for code in code_order:
        a = [1 if code in set(validA[t].get(field) or []) else 0 for t in shared_tids]
        b = [1 if code in set(validB[t].get(field) or []) else 0 for t in shared_tids]
        per_code[code] = {
            "kappa": cohen_kappa_binary(a, b),
            "present_A": sum(a), "present_B": sum(b),
            "agreement": sum(1 for x, y in zip(a, b) if x == y) / n,
        }
    jac, exact = [], 0
    for t in shared_tids:
        sa = set(validA[t].get(field) or [])
        sb = set(validB[t].get(field) or [])
        union = sa | sb
        jac.append(1.0 if not union else len(sa & sb) / len(union))
        if sa == sb:
            exact += 1
    kappas = [v["kappa"] for v in per_code.values()]
    return {
        "n_shared": n,
        "metric_note": "per-code Cohen's kappa (binarize presence); Jaccard of two "
                       "empty sets := 1.0; exact = identical id-sets.",
        "per_code_kappa": per_code,
        "mean_kappa_defined_codes": _mean(kappas),
        "n_codes_kappa_undefined": sum(1 for k in kappas if k is None),
        "mean_jaccard": _mean(jac),
        "exact_set_match_rate": exact / n,
    }


def compute_irr(sset: str, coder_valids: dict, vocab: dict) -> dict:
    slugs = [s for s, v in coder_valids.items() if v is not None]
    if len(slugs) < 2:
        return {"status": "pending_census",
                "note": f"need 2 coders with codings; have {slugs}"}
    a, b = sorted(slugs)[:2]
    va, vb = coder_valids[a], coder_valids[b]
    shared = sorted(set(va) & set(vb))
    nc_shared = [t for t in shared
                 if verdict_of(va[t]) in NC_VERDICTS and verdict_of(vb[t]) in NC_VERDICTS]
    return {
        "coders": [a, b],
        "mechanisms": irr_block(shared, va, vb, vocab["mech_order"], "mechanism_ids"),
        "errors": irr_block(nc_shared, va, vb, vocab["err_order"], "error_ids"),
    }


# --------------------------------------------------------------------------- #
# Flip sub-study (rerun_divergent) -- 1:1 by question_id
# --------------------------------------------------------------------------- #
def flip_pairs(rd_by_qid: dict, orig_by_qid: dict) -> tuple:
    """Classify each divergent qid (verdicts from the authoritative records).

    Decision (b): the flip axis is CORRECT-path vs NON-CORRECT-path (non-correct
    = wrong u abstained), folding abstention in. Return (contrast_pairs,
    noncorrect_pairs):
      - contrast_pairs: exactly one side is 'correct'; the other is the
        non-correct path (wrong OR abstained). 66 correct<->wrong + 5
        correct<->abstained = 71. Each carries ``noncorrect_verdict``.
      - noncorrect_pairs: neither side is correct (wrong<->abstained, 9) -> no
        correct path; reported separately as failure-mode divergence.
    """
    contrast, noncorrect = [], []
    for qid, rd_rec in sorted(rd_by_qid.items()):
        orig_rec = orig_by_qid.get(qid)
        ov = orig_rec["verdict"] if orig_rec else None
        rv = rd_rec["verdict"]
        pair = {
            "question_id": qid,
            "orig_verdict": ov,
            "rd_verdict": rv,
            "orig_key": f"q{qid}_r0_{ov}" if orig_rec else None,
            "rd_key": f"q{qid}_r0_{rv}",
        }
        if ov == "correct" or rv == "correct":
            pair["noncorrect_verdict"] = rv if ov == "correct" else ov
            contrast.append(pair)
        else:
            noncorrect.append(pair)  # wrong<->abstained: no correct path
    return contrast, noncorrect


def flip_residual(noncorrect_pairs, orig_valid, rd_valid, vocab, coder_label) -> dict:
    """Aggregate the wrong<->abstained residual (no correct path) for ONE coder:
    which errors sit on the wrong side vs the abstained side, and what mechanisms
    differ -- 'what went differently to reach these two failure outcomes'."""
    def member(pair, is_orig):
        d = orig_valid if is_orig else rd_valid
        key = pair["orig_key"] if is_orig else pair["rd_key"]
        if d is None or key not in d or is_stub(d[key]):
            return None
        return d[key]

    err_wrong, err_abst = Counter(), Counter()
    mech_only_wrong, mech_only_abst = Counter(), Counter()
    resolved, skipped, detail = 0, 0, []
    for p in noncorrect_pairs:
        orig_is_wrong = p["orig_verdict"] == "wrong"
        wrong_m = member(p, is_orig=orig_is_wrong)
        abst_m = member(p, is_orig=not orig_is_wrong)
        if wrong_m is None or abst_m is None:
            skipped += 1
            continue
        resolved += 1
        we = set(wrong_m.get("error_ids") or [])
        ae = set(abst_m.get("error_ids") or [])
        err_wrong.update(we); err_abst.update(ae)
        wmech = set(wrong_m.get("mechanism_ids") or [])
        amech = set(abst_m.get("mechanism_ids") or [])
        mech_only_wrong.update(wmech - amech)
        mech_only_abst.update(amech - wmech)
        detail.append({"question_id": p["question_id"],
                       "wrong_errors": sorted(we), "abstained_errors": sorted(ae)})
    return {"coder": coder_label, "n_pairs": len(noncorrect_pairs),
            "pairs_resolved": resolved, "skipped": skipped,
            "errors_on_wrong_side": dict(err_wrong),
            "errors_on_abstained_side": dict(err_abst),
            "mechanisms_only_on_wrong_side": dict(mech_only_wrong),
            "mechanisms_only_on_abstained_side": dict(mech_only_abst),
            "detail": detail}


def flip_contrast(contrast_pairs, noncorrect_pairs, orig_valid, rd_valid, vocab, coder_label):
    """Aggregate the CORRECT-path vs NON-CORRECT-path contrast for ONE coder
    (decision b). The pooled contrast is built by pool_flip (sum of per-coder
    results), not by merging valids here."""
    def member(pair, is_orig):
        d = orig_valid if is_orig else rd_valid
        key = pair["orig_key"] if is_orig else pair["rd_key"]
        if d is None or key not in d or is_stub(d[key]):
            return None
        return d[key]

    result = {
        "coder": coder_label,
        "n_contrast_pairs": len(contrast_pairs),
        "n_correct_vs_wrong": sum(
            1 for p in contrast_pairs if p["noncorrect_verdict"] == "wrong"),
        "n_correct_vs_abstained": sum(
            1 for p in contrast_pairs if p["noncorrect_verdict"] == "abstained"),
        "n_noncorrect_pairs": len(noncorrect_pairs),
        "skipped_pairs": [],
        "pairs_resolved": 0,
    }
    err_on_nc = Counter()
    err_on_nc_by_track = {"agent": Counter(), "non-agent": Counter()}
    mech_unique_correct = Counter()
    mech_unique_noncorrect = Counter()

    for p in contrast_pairs:
        orig_is_correct = p["orig_verdict"] == "correct"
        correct_m = member(p, is_orig=orig_is_correct)
        nc_m = member(p, is_orig=not orig_is_correct)
        if correct_m is None or nc_m is None:
            result["skipped_pairs"].append(
                {"question_id": p["question_id"],
                 "reason": "member missing or stub (pending census / flagged)"})
            continue
        result["pairs_resolved"] += 1
        nc_errs = set(nc_m.get("error_ids") or [])
        for e in nc_errs:
            err_on_nc[e] += 1
            track = vocab["err"].get(e, {}).get("track")
            if track in err_on_nc_by_track:
                err_on_nc_by_track[track][e] += 1
        cm = set(correct_m.get("mechanism_ids") or [])
        ncm = set(nc_m.get("mechanism_ids") or [])
        for m in cm - ncm:
            mech_unique_correct[m] += 1
        for m in ncm - cm:
            mech_unique_noncorrect[m] += 1

    result["errors_on_noncorrect_path"] = dict(err_on_nc)
    result["errors_on_noncorrect_path_by_track"] = {
        k: dict(v) for k, v in err_on_nc_by_track.items()}
    result["mechanisms_unique_to_correct_path"] = dict(mech_unique_correct)
    result["mechanisms_unique_to_noncorrect_path"] = dict(mech_unique_noncorrect)
    result["residual_wrong_vs_abstained"] = flip_residual(
        noncorrect_pairs, orig_valid, rd_valid, vocab, coder_label)
    if result["pairs_resolved"] == 0:
        result["status"] = "pending_census"
    return result


def pool_flip(per_coder_results: list) -> dict:
    """Pool the flip contrast across coders by SUMMING each coder's contribution.

    Observation model = (coder, qid-pair): a qid-pair coded by BOTH coders
    contributes twice, exactly matching the per-(coder,trace) observation model
    used by pool_mech / pool_err / pool_honest. (The previous first-coder-wins
    ``merge`` counted each qid once and was inconsistent with every other pooled
    table.) Per-coder flip outputs are unchanged; this only rebuilds the pool.
    """
    results = [r for r in per_coder_results if r is not None]
    if not results:
        return {"status": "pending_census"}
    err_on_nc = Counter()
    err_by_track = {"agent": Counter(), "non-agent": Counter()}
    mech_unique_correct = Counter()
    mech_unique_noncorrect = Counter()
    res_err_wrong, res_err_abst = Counter(), Counter()
    skipped = []
    pairs_resolved = res_pairs_resolved = 0
    for r in results:
        pairs_resolved += r.get("pairs_resolved", 0)
        err_on_nc.update(r.get("errors_on_noncorrect_path", {}))
        for track in ("agent", "non-agent"):
            err_by_track[track].update(
                r.get("errors_on_noncorrect_path_by_track", {}).get(track, {}))
        mech_unique_correct.update(r.get("mechanisms_unique_to_correct_path", {}))
        mech_unique_noncorrect.update(r.get("mechanisms_unique_to_noncorrect_path", {}))
        res = r.get("residual_wrong_vs_abstained", {})
        res_pairs_resolved += res.get("pairs_resolved", 0)
        res_err_wrong.update(res.get("errors_on_wrong_side", {}))
        res_err_abst.update(res.get("errors_on_abstained_side", {}))
        skipped.extend({**s, "coder": r.get("coder")}
                       for s in r.get("skipped_pairs", []))
    # pair populations are coder-independent (same for all coders).
    out = {
        "coder": "pooled",
        "observation_model": "sum over coders of (coder, qid-pair) contrasts; a "
                             "qid-pair coded by both coders contributes twice",
        "n_coders_pooled": len(results),
        "n_contrast_pairs": results[0]["n_contrast_pairs"],
        "n_correct_vs_wrong": results[0]["n_correct_vs_wrong"],
        "n_correct_vs_abstained": results[0]["n_correct_vs_abstained"],
        "n_noncorrect_pairs": results[0]["n_noncorrect_pairs"],
        "pairs_resolved": pairs_resolved,
        "skipped_pairs": skipped,
        "errors_on_noncorrect_path": dict(err_on_nc),
        "errors_on_noncorrect_path_by_track": {k: dict(v) for k, v in err_by_track.items()},
        "mechanisms_unique_to_correct_path": dict(mech_unique_correct),
        "mechanisms_unique_to_noncorrect_path": dict(mech_unique_noncorrect),
        "residual_wrong_vs_abstained": {
            "n_pairs": results[0]["residual_wrong_vs_abstained"]["n_pairs"],
            "pairs_resolved": res_pairs_resolved,
            "errors_on_wrong_side": dict(res_err_wrong),
            "errors_on_abstained_side": dict(res_err_abst),
        },
    }
    if pairs_resolved == 0:
        out["status"] = "pending_census"
    return out


# --------------------------------------------------------------------------- #
# Human sanity-check dump (mirror build_review_sample.py sampler)
# --------------------------------------------------------------------------- #
def build_sample_records(coded: dict, records: dict) -> list:
    """One record per (set, trace) coded non-stub by >=1 coder, enriched with the
    records-file verdict/qid so brs.stratified_sample can stratify by (set,verdict)."""
    seen = set()
    out = []
    for sset, coder_valids in coded.items():
        by_qid = records["orig_by_qid"] if sset == "orig" else records["rd_by_qid"]
        tids = set()
        for v in coder_valids.values():
            if v is not None:
                tids |= set(v)
        for tid in sorted(tids):
            p = parse_tid(tid)
            if p is None or (sset, tid) in seen:
                continue
            seen.add((sset, tid))
            rec = by_qid.get(p[0], {})
            out.append({"set": sset, "trace_id": tid, "question_id": p[0],
                        "verdict": p[2], "project": rec.get("project"),
                        "category": rec.get("category")})
    return out


def render_sanity_sample(sampled, coded, trace_dir) -> str:
    L = []
    w = L.append
    w("# Census sanity-check sample")
    w("")
    w(f"_Generated {date.today().isoformat()} · deterministic, no LLM · read-only._")
    w("")
    comp = Counter((r["set"], r["verdict"]) for r in sampled)
    w("| set | correct | wrong | abstained | total |")
    w("| --- | --: | --: | --: | --: |")
    for s in SETS:
        row = [comp.get((s, v), 0) for v in VERDICTS]
        if sum(row):
            w(f"| `{s}` | {row[0]} | {row[1]} | {row[2]} | {sum(row)} |")
    w("")
    for idx, r in enumerate(sampled, 1):
        sset, tid = r["set"], r["trace_id"]
        q, pred, gt, _ = brs.read_trace_text(trace_dir, sset, tid)
        w("---\n")
        w(f"## {idx}. `{tid}` — {r['verdict']} · {sset}")
        w(f"- qid {r['question_id']} · project {r.get('project')} · cat {r.get('category')}\n")
        w("### Question\n")
        w(q or "_(unavailable)_")
        w("\n### Agent answer\n")
        w(pred or "_(unavailable)_")
        w("\n### Reference answer\n")
        w(gt or "_(unavailable)_")
        w("")
        for slug, coder_valids in coded[sset].items():
            obj = coder_valids.get(tid) if coder_valids else None
            w(f"### Coder `{slug}`\n")
            if obj is None:
                w("_(not coded)_\n")
                continue
            if is_stub(obj):
                w(f"_(stub: {obj.get('_error')})_\n")
                continue
            mids = obj.get("mechanism_ids") or []
            eids = obj.get("error_ids") or []
            ev = obj.get("evidence") or {}
            w(f"- **mechanisms:** {', '.join(mids) or '_(none)_'}")
            w(f"- **errors:** {', '.join(eids) or '_(none)_'}")
            for k in list(mids) + list(eids):
                if k in ev:
                    w(f"  - `{k}`: {ev[k]}")
            w("")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- #
# Pool raw counters
# --------------------------------------------------------------------------- #
def pool_mech(raws: list, vocab: dict) -> dict:
    codes = {m: {"present": 0, "correct_present": 0, "wrong_present": 0}
             for m in vocab["mech_order"]}
    agg = {"n": 0, "n_correct": 0, "n_wrong": 0, "codes": codes,
           "umbrella_union": {"present": 0, "correct_present": 0},
           "schema_ids": sorted(vocab["umbrella"].get("schema-structure-discovery", []))}
    for r in raws:
        agg["n"] += r["n"]; agg["n_correct"] += r["n_correct"]; agg["n_wrong"] += r["n_wrong"]
        agg["umbrella_union"]["present"] += r["umbrella_union"]["present"]
        agg["umbrella_union"]["correct_present"] += r["umbrella_union"]["correct_present"]
        for m, c in r["codes"].items():
            d = agg["codes"].setdefault(m, {"present": 0, "correct_present": 0, "wrong_present": 0})
            for k in c:
                d[k] += c[k]
    return agg


def pool_err(raws: list, vocab: dict) -> dict:
    agg = {"n_nc": 0, "codes": {e: 0 for e in vocab["err_order"]},
           "n_solely_exogenous": 0, "solely_exo_ids": [],
           "n_empty_error_set": 0, "empty_ids": []}
    for r in raws:
        agg["n_nc"] += r["n_nc"]
        agg["n_solely_exogenous"] += r["n_solely_exogenous"]
        agg["n_empty_error_set"] += r["n_empty_error_set"]
        agg["solely_exo_ids"] += r["solely_exo_ids"]
        agg["empty_ids"] += r["empty_ids"]
        for e, c in r["codes"].items():
            agg["codes"][e] = agg["codes"].get(e, 0) + c
    return agg


def pool_honest(raws: list) -> dict:
    keys = ("n_all", "n_wrong", "n_abstained", "n_nc", "n_purely_exo", "n_empty",
            "n_sys", "n_pres", "n_core", "abst_e14", "abst_e7",
            "abst_purely_exo", "abst_empty")
    agg = {k: 0 for k in keys}
    for r in raws:
        for k in keys:
            agg[k] += r.get(k, 0)
    if raws:
        agg["nc_basis"] = raws[0].get("nc_basis", "wrong-only")
    return agg


# --------------------------------------------------------------------------- #
# Writers
# --------------------------------------------------------------------------- #
def _dump_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def _pct(x):
    return "—" if x is None else f"{100 * x:.1f}%"


def mech_md(sset, per_coder_reports, pooled_report, vocab) -> str:
    L = [f"# Mechanisms (RQ2) — {sset}", ""]
    for label, rep in list(per_coder_reports.items()) + [(POOLED_LABEL, pooled_report)]:
        L.append(f"## {label}")
        if rep.get("status") == "pending_census":
            L.append("_pending census (0 traces)_\n"); continue
        L.append(f"- traces: {rep['n_traces']} · P(correct) baseline: {_pct(rep['baseline_p_correct'])}")
        uu = rep["schema_umbrella_union"]
        L.append(f"- **schema-structure-discovery UNION** ({'∪'.join(uu['member_ids'])}): "
                 f"prevalence {_pct(uu['prevalence'])} ({uu['present']}/{uu['denominator']})")
        L.append("")
        L.append("| M | name | prevalence | n | P(correct\\|m) | lift | P(m\\|correct) | P(m\\|wrong) |")
        L.append("| --- | --- | --: | --: | --: | --: | --: | --: |")
        for m, d in rep["mechanisms"].items():
            lift = "—" if d["lift_vs_baseline"] is None else f"{d['lift_vs_baseline']:.2f}"
            L.append(f"| {m} | {d['name'][:32]} | {_pct(d['prevalence'])} | {d['present']} | "
                     f"{_pct(d['conditional_accuracy_p_correct_given_m'])} | {lift} | "
                     f"{_pct(d['p_m_given_correct'])} | {_pct(d['p_m_given_wrong'])} |")
        L.append("")
    return "\n".join(L) + "\n"


def err_md(sset, per_coder_reports, pooled_report, vocab) -> str:
    L = [f"# Errors (RQ3) — {sset}", "", "_Over NC = wrong ∪ abstained (non-stub)._", ""]
    for label, rep in list(per_coder_reports.items()) + [(POOLED_LABEL, pooled_report)]:
        L.append(f"## {label}")
        if rep.get("status") == "pending_census":
            L.append("_pending census (0 NC traces)_\n"); continue
        L.append(f"- NC traces: {rep['n_nc']}")
        L.append(f"- solely-exogenous: {rep['n_solely_exogenous']} ({_pct(rep['share_solely_exogenous'])})")
        L.append(f"- empty error set (coder gap, flagged): {rep['n_empty_error_set']} "
                 f"({_pct(rep['share_empty_error_set'])})")
        L.append("")
        for block, title in (("agent_track", "Agent track"), ("non_agent_track", "Non-agent / exogenous")):
            L.append(f"**{title}**")
            L.append("| E | name | prevalence | n |")
            L.append("| --- | --- | --: | --: |")
            for e, d in rep[block].items():
                L.append(f"| {e} | {d['name'][:34]} | {_pct(d['prevalence'])} | {d['present']} |")
            L.append("")
    return "\n".join(L) + "\n"


def honest_md(sset, per_coder_reports, pooled_report) -> str:
    L = [f"# Layered honest error rate — {sset}", ""]
    L.append("_Peel (c) `transparency-only` is over the coder-specific SYS set; it is a "
             "DIFFERENT population from `judge_decomp.transparency_only`, which is over "
             "ALL wrong records (coder-independent). Different denominators by design._")
    L.append("")
    for label, rep in list(per_coder_reports.items()) + [(POOLED_LABEL, pooled_report)]:
        L.append(f"## {label}")
        if rep.get("status") == "pending_census":
            L.append("_pending census (0 traces)_\n"); continue
        n = rep["n_traces"]
        a = rep["peel_a_raw"]; b = rep["peel_b_system_attributable"]; c = rep["peel_c_core_capability"]
        ab = rep["abstained_outcome"]
        L.append(f"- base T (all non-stub): {n} · chain base (decision a): **{rep['nc_basis']}**")
        L.append(f"- **(a) raw** — wrong-only {a['wrong_only']['count']}/{n} "
                 f"({_pct(a['wrong_only']['rate'])}); wrong+abstained {a['wrong_plus_abstained']['count']}/{n} "
                 f"({_pct(a['wrong_plus_abstained']['rate'])})")
        L.append(f"- **(b) system-attributable** — {b['count']}/{n} ({_pct(b['rate'])}); "
                 f"peeled {b['n_purely_exogenous_peeled']} purely-exogenous; "
                 f"kept {b['n_empty_error_set_kept_flagged']} empty-error (flagged)")
        L.append(f"- **(c) core-capability** — {c['count']}/{n} ({_pct(c['rate'])}); "
                 f"peeled {c['n_transparency_only_peeled']} transparency-only")
        L.append(f"- _abstained (own outcome, not in chain): {ab['count']}/{n} "
                 f"({_pct(ab['rate'])}); E14-infra {ab['n_with_E14_infra']}, "
                 f"E7-judge {ab['n_with_E7_judge']}, purely-exogenous {ab['n_purely_exogenous']}_")
        L.append("")
    return "\n".join(L) + "\n"


def flip_md(contrast, noncorrect, per_coder, pooled, vocab) -> str:
    L = ["# Flip sub-study (rerun_divergent)", ""]
    L.append("_Decision (b): axis = CORRECT-path vs NON-CORRECT-path (non-correct = "
             "wrong ∪ abstained), folding abstention in._")
    L.append(f"- contrast pairs (one side correct): **{len(contrast)}** "
             f"(correct↔wrong + correct↔abstained)")
    L.append(f"- residual wrong↔abstained pairs (no correct path, reported separately): "
             f"**{len(noncorrect)}**")
    L.append("- Pairing: 1:1 by question_id (records = authoritative verdict); key = `q{qid}_r0_{verdict}`.")
    L.append("")
    for label, rep in list(per_coder.items()) + [("pooled", pooled)]:
        L.append(f"## {label}")
        if rep.get("status") == "pending_census":
            L.append(f"_pending census — 0/{rep['n_contrast_pairs']} contrast pairs resolved "
                     f"({len(rep['skipped_pairs'])} skipped: rd codings absent/stub)_\n")
            continue
        L.append(f"- resolved {rep['pairs_resolved']}/{rep['n_contrast_pairs']} contrast pairs "
                 f"(= {rep['n_correct_vs_wrong']} correct↔wrong + "
                 f"{rep['n_correct_vs_abstained']} correct↔abstained; "
                 f"{len(rep['skipped_pairs'])} skipped)")
        L.append(f"- errors on NON-CORRECT path (by track): {rep['errors_on_noncorrect_path_by_track']}")
        L.append(f"- mechanisms UNIQUE to correct path: {rep['mechanisms_unique_to_correct_path']}")
        res = rep["residual_wrong_vs_abstained"]
        L.append(f"- residual wrong↔abstained ({res['pairs_resolved']}/{res['n_pairs']} resolved): "
                 f"errors on wrong side {res['errors_on_wrong_side']}, "
                 f"on abstained side {res['errors_on_abstained_side']}")
        L.append("")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- #
# Reconciliation + orchestration
# --------------------------------------------------------------------------- #
def reconcile_flagged(census_dir, slug, sset, stubs, warnings, strict):
    state_flagged = load_state_flagged(census_dir, slug, sset)
    stub_ids = set(stubs)
    note = {"slug": slug, "set": sset, "n_flagged_codings": len(stub_ids),
            "flagged_ids": sorted(stub_ids), "state_flagged": state_flagged}
    if state_flagged is not None and set(state_flagged) != stub_ids:
        msg = (f"[reconcile] {slug}/{sset}: codings _error keys {sorted(stub_ids)} != "
               f"_state.flagged {sorted(state_flagged)} (codings-dict authoritative)")
        warnings.append(msg)
        note["mismatch"] = True
        if strict:
            raise SystemExit("strict: " + msg)
    return note


def run(args) -> int:
    warnings: list[str] = []
    vocab = load_vocab(args.mechanisms, args.errors)
    records = load_records(args.records)
    sets = SETS if args.set == "all" else (args.set,)

    # auto-detect coders
    if args.coders:
        coders = [c.strip() for c in args.coders.split(",") if c.strip()]
    else:
        coders = sorted(
            d for d in os.listdir(args.census_dir)
            if os.path.isdir(os.path.join(args.census_dir, d))
            and any(f.endswith(".codings.json")
                    for f in os.listdir(os.path.join(args.census_dir, d)))
        )
    db_for = {"orig": args.orig_db, "rerun_divergent": args.rerun_db}

    outdir = args.outdir
    os.makedirs(outdir, exist_ok=True)
    coded: dict[str, dict] = {}          # set -> {slug: valid|None}
    flagged_notes = []
    summary = {"generated": date.today().isoformat(), "coders": coders,
               "sets": {}, "warnings": warnings, "reconciliation": flagged_notes}

    for sset in sets:
        set_out = os.path.join(outdir, sset)
        os.makedirs(set_out, exist_ok=True)
        judge = load_judge(db_for[sset])
        per_coder_valid = {}
        mech_raws, err_raws, honest_raws = [], [], []
        mech_reports, err_reports, honest_reports = {}, {}, {}

        for slug in coders:
            loaded = load_codings(args.census_dir, slug, sset)
            if loaded is None:
                per_coder_valid[slug] = None
                continue
            valid, stubs = loaded
            per_coder_valid[slug] = valid
            flagged_notes.append(
                reconcile_flagged(args.census_dir, slug, sset, stubs, warnings, args.strict))
            mr = mech_raw(valid, vocab); er = err_raw(valid, vocab)
            hr = honest_raw(valid, judge, vocab, args.nc_basis)
            mech_raws.append(mr); err_raws.append(er); honest_raws.append(hr)
            mech_reports[slug] = mech_report(mr, vocab)
            err_reports[slug] = err_report(er, vocab)
            honest_reports[slug] = honest_report(hr)

            # empty-error-set escalation signal
            if er["n_empty_error_set"] and er["n_nc"]:
                rate = er["n_empty_error_set"] / er["n_nc"]
                if rate > 0.05:
                    warnings.append(
                        f"[escalate?] {slug}/{sset}: empty-error-set rate {rate:.1%} "
                        f"({er['n_empty_error_set']}/{er['n_nc']}) on NC traces")

        coded[sset] = per_coder_valid
        present = [s for s in coders if per_coder_valid.get(s) is not None]

        # pooled
        pooled_mech = mech_report(pool_mech(mech_raws, vocab), vocab) if mech_raws \
            else {"status": "pending_census"}
        pooled_err = err_report(pool_err(err_raws, vocab), vocab) if err_raws \
            else {"status": "pending_census"}
        pooled_honest = honest_report(pool_honest(honest_raws)) if honest_raws \
            else {"status": "pending_census"}

        _dump_json(os.path.join(set_out, "mechanisms.json"),
                   {"set": sset, "per_coder": mech_reports, "pooled": pooled_mech})
        _dump_json(os.path.join(set_out, "errors.json"),
                   {"set": sset, "per_coder": err_reports, "pooled": pooled_err})
        _dump_json(os.path.join(set_out, "honest_rate.json"),
                   {"set": sset, "per_coder": honest_reports, "pooled": pooled_honest})
        _dump_json(os.path.join(set_out, "judge_decomp.json"),
                   {"set": sset, **judge_decomp(records["by_set"].get(sset, []), judge)})
        _dump_json(os.path.join(set_out, "irr.json"),
                   compute_irr(sset, per_coder_valid, vocab))
        _dump_json(os.path.join(set_out, "combined.json"),
                   {"set": sset,
                    "note": "per-judge + pooled (N-coder sum: 2x denom when both "
                            "coders coded a trace, 1x if only one present); observation "
                            "= (coder,trace), excluding each coder's OWN stubs; NEVER "
                            "pooled across sets.",
                    "mechanisms": {"per_judge": mech_reports, "pooled": pooled_mech},
                    "errors": {"per_judge": err_reports, "pooled": pooled_err},
                    "honest_rate": {"per_judge": honest_reports, "pooled": pooled_honest}})

        with open(os.path.join(set_out, "mechanisms.md"), "w") as f:
            f.write(mech_md(sset, mech_reports, pooled_mech, vocab))
        with open(os.path.join(set_out, "errors.md"), "w") as f:
            f.write(err_md(sset, err_reports, pooled_err, vocab))
        with open(os.path.join(set_out, "honest_rate.md"), "w") as f:
            f.write(honest_md(sset, honest_reports, pooled_honest))

        # flip study (rerun_divergent only)
        if sset == "rerun_divergent":
            contrast, noncorrect = flip_pairs(records["rd_by_qid"], records["orig_by_qid"])
            orig_valids = coded.get("orig", {})
            per_coder_flip = {}
            for slug in coders:
                ov = orig_valids.get(slug)
                rv = per_coder_valid.get(slug)
                if ov is None and rv is None:
                    continue
                per_coder_flip[slug] = flip_contrast(contrast, noncorrect, ov, rv, vocab, slug)
            # pooled: SUM each coder's flip contribution -- observation = (coder,
            # qid-pair), so a qid-pair coded by both coders contributes twice.
            # Consistent with pool_mech/err/honest; replaces the old first-coder-wins
            # merge (which counted each qid once and under-counted the pool).
            pooled_flip = pool_flip(list(per_coder_flip.values()))
            _dump_json(os.path.join(set_out, "flip_study.json"),
                       {"axis": "correct-path vs non-correct-path (decision b)",
                        "n_contrast_pairs": len(contrast),
                        "n_noncorrect_pairs": len(noncorrect),
                        "contrast_pairs": contrast, "noncorrect_pairs": noncorrect,
                        "per_coder": per_coder_flip, "pooled": pooled_flip})
            with open(os.path.join(set_out, "flip_study.md"), "w") as f:
                f.write(flip_md(contrast, noncorrect, per_coder_flip, pooled_flip, vocab))

        summary["sets"][sset] = {
            "coders_present": present,
            "mechanisms_pooled": pooled_mech.get("schema_umbrella_union")
            if pooled_mech.get("status") != "pending_census" else "pending_census",
            "honest_pooled": pooled_honest,
        }

    # human sanity sample (over all coded sets in scope)
    if args.sample_n and any(any(v is not None for v in cv.values()) for cv in coded.values()):
        sample_recs = build_sample_records(coded, records)
        if sample_recs:
            sampled, _alloc = brs.stratified_sample(
                sample_recs, args.sample_n, min_per=3, seed=args.seed)
            with open(os.path.join(outdir, "sanity_sample.md"), "w") as f:
                f.write(render_sanity_sample(sampled, coded, args.trace_dir))

    _dump_json(os.path.join(outdir, "summary.json"), summary)
    with open(os.path.join(outdir, "summary.md"), "w") as f:
        f.write(render_summary_md(summary))

    print(f"wrote analysis -> {outdir}")
    for w in warnings:
        print("  WARN:", w, file=sys.stderr)
    return 0


def render_summary_md(summary) -> str:
    L = ["# Census analysis summary", "",
         f"_Generated {summary['generated']} · coders: {', '.join(summary['coders'])}_", ""]
    for sset, s in summary["sets"].items():
        L.append(f"## {sset}")
        L.append(f"- coders present: {', '.join(s['coders_present']) or '_(none)_'}")
        uu = s["mechanisms_pooled"]
        if uu == "pending_census":
            L.append("- mechanisms: _pending census_")
        else:
            L.append(f"- schema-union prevalence (pooled): {_pct(uu['prevalence'])} "
                     f"({uu['present']}/{uu['denominator']})")
        h = s["honest_pooled"]
        if h.get("status") == "pending_census":
            L.append("- honest rate: _pending census_")
        else:
            base = h.get("nc_basis", "wrong-only")
            raw_key = "wrong_only" if base == "wrong-only" else "wrong_plus_abstained"
            ab = h["abstained_outcome"]
            L.append(f"- honest error rate (pooled, chain base {base}): raw {_pct(h['peel_a_raw'][raw_key]['rate'])} "
                     f"→ system {_pct(h['peel_b_system_attributable']['rate'])} "
                     f"→ core {_pct(h['peel_c_core_capability']['rate'])}; "
                     f"abstained (own outcome) {_pct(ab['rate'])}")
        L.append("")
    if summary["warnings"]:
        L.append("## Warnings")
        for w in summary["warnings"]:
            L.append(f"- {w}")
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------- #
# Self-test (synthetic fixtures + live checks; NO writes)
# --------------------------------------------------------------------------- #
def self_test(args) -> int:
    vocab = load_vocab(args.mechanisms, args.errors)
    non_agent = vocab["non_agent_ids"]
    assert non_agent == {"E7", "E14"}, non_agent
    schema = set(vocab["umbrella"]["schema-structure-discovery"])
    assert schema == {"M1", "M2", "M3", "M4"}, schema

    # --- Test 2: peel set-arithmetic on a synthetic fixture ---
    valid = {
        "q1_r0_wrong": {"verdict": "wrong", "error_ids": ["E4a", "E7"]},   # mixed -> KEPT
        "q2_r0_wrong": {"verdict": "wrong", "error_ids": ["E7", "E14"]},   # pure exo -> peeled(b)
        "q3_r0_wrong": {"verdict": "wrong", "error_ids": ["E4a"]},          # transparency-only -> peeled(c)
        "q4_r0_wrong": {"verdict": "wrong", "error_ids": ["E2"]},           # agent -> CORE
        "q5_r0_correct": {"verdict": "correct", "error_ids": []},           # correct, not NC
        "q6_r0_abstained": {"verdict": "abstained", "error_ids": ["E4a"]},  # abstained: own outcome
        "q7_r0_abstained": {"verdict": "abstained", "error_ids": ["E14"]},  # abstained: E14-infra
    }
    judge = {
        (1, 0): {"faithfulness": "No", "completeness": "Yes", "transparency": "Yes", "relevance": "Yes"},
        (2, 0): {"faithfulness": "No", "completeness": "No", "transparency": "No", "relevance": "No"},
        (3, 0): {"faithfulness": "Yes", "completeness": "Yes", "transparency": "No", "relevance": "Yes"},
        (4, 0): {"faithfulness": "No", "completeness": "Yes", "transparency": "Yes", "relevance": "Yes"},
        (6, 0): {"faithfulness": "Na", "completeness": "Na", "transparency": "Na", "relevance": "Na"},
        (7, 0): {"faithfulness": "Na", "completeness": "Na", "transparency": "Na", "relevance": "Na"},
    }
    # Decision (a): default wrong-only chain -- abstained is its OWN outcome, not peeled.
    hr = honest_raw(valid, judge, vocab)
    assert hr["nc_basis"] == "wrong-only", hr
    assert hr["n_all"] == 7 and hr["n_nc"] == 6, hr           # 4 wrong + 2 abstained
    assert hr["n_wrong"] == 4 and hr["n_abstained"] == 2, hr
    assert hr["abst_e14"] == 1 and hr["abst_purely_exo"] == 1, hr  # q7 E14-only
    assert hr["n_purely_exo"] == 1, hr        # q2 peeled at (b); abstained OUT of chain
    assert hr["n_sys"] == 3, hr               # q1,q3,q4 (wrong-only chain; q6/q7 excluded)
    assert hr["n_pres"] == 1, hr              # q3 transparency-only
    assert hr["n_core"] == 2, hr              # q1,q4
    print("PASS test2 (wrong-only): mixed KEPT, purely-exo peeled@b, transparency-only "
          f"removed@c (sys={hr['n_sys']} core={hr['n_core']}); abstained own outcome "
          f"n={hr['n_abstained']} (E14={hr['abst_e14']})")
    # wrong-plus-abstained basis folds the abstained agent-error trace (q6) into the chain.
    hr2 = honest_raw(valid, judge, vocab, nc_basis="wrong-plus-abstained")
    assert hr2["n_sys"] == 4 and hr2["n_core"] == 3, hr2      # q6 folded in (q7 pure-exo peeled@b)
    print(f"PASS test2b (wrong+abstained folded): sys={hr2['n_sys']} core={hr2['n_core']}")

    # --- Test 4: transparency-only guards Na (abstained all-Na never matches) ---
    judge_na = {(9, 0): {"faithfulness": "Na", "completeness": "Na",
                         "transparency": "Na", "relevance": "Na"}}
    assert transparency_only(judge_na, "q9_r0_abstained") is False
    assert transparency_only({(3, 0): judge[(3, 0)]}, "q3_r0_wrong") is True
    print("PASS test4: transparency-only Na-guarded")

    # --- Test 3: flip fold (decision b) -> 71 contrast + 9 residual ---
    records = load_records(args.records)
    contrast, noncorrect = flip_pairs(records["rd_by_qid"], records["orig_by_qid"])
    assert len(contrast) == 71, len(contrast)          # 66 correct<->wrong + 5 correct<->abstained
    assert len(noncorrect) == 9, len(noncorrect)       # wrong<->abstained, no correct path
    n_cw = sum(1 for p in contrast if p["noncorrect_verdict"] == "wrong")
    n_ca = sum(1 for p in contrast if p["noncorrect_verdict"] == "abstained")
    assert n_cw == 66 and n_ca == 5, (n_cw, n_ca)
    for p in contrast:
        assert "correct" in {p["orig_verdict"], p["rd_verdict"]}
    for p in noncorrect:
        assert "correct" not in {p["orig_verdict"], p["rd_verdict"]}
    for p in contrast + noncorrect:
        assert p["orig_key"].startswith("q") and p["rd_key"].startswith("q")
    print(f"PASS test3: flip fold 71 contrast ({n_cw} correct↔wrong + {n_ca} "
          f"correct↔abstained) + 9 residual wrong↔abstained; keys well-formed")

    # --- Test 1: stub exclusion (synthetic) + live reconciliation ---
    # (a) Synthetic fixture: partition by is_stub the way load_codings does, so
    #     the invariant is checked against injected data, never live census state
    #     (the census is fully repaired -> 0 live stubs, but the rule must hold).
    fixture = {
        "qX_r0_correct": {"verdict": "correct", "error_ids": []},
        "qY_r0_wrong": {"verdict": "wrong", "error_ids": ["E2"]},
        "qZ_r0_stub": {"_error": "timeout"},
    }
    fvalid = {k: v for k, v in fixture.items() if not is_stub(v)}
    fstubs = {k: v for k, v in fixture.items() if is_stub(v)}
    assert set(fstubs) == {"qZ_r0_stub"}, fstubs        # only _error is a stub
    assert "qZ_r0_stub" not in fvalid, "stub leaked into valid"
    assert set(fvalid) == {"qX_r0_correct", "qY_r0_wrong"}, fvalid

    # (b) Live reconciliation invariant: detected stubs (codings with _error)
    #     must equal _state.flagged for each coded set. Post-repair both are
    #     empty, which must still reconcile cleanly.
    loaded = load_codings(args.census_dir, "minimax-m3", "orig")
    assert loaded is not None, "minimax orig codings absent"
    mvalid, mstubs = loaded
    state_flagged = load_state_flagged(args.census_dir, "minimax-m3", "orig")
    assert set(state_flagged or []) == set(mstubs), (state_flagged, list(mstubs))
    print(f"PASS test1: synthetic stub excluded; live n_flagged={len(mstubs)} "
          f"reconciles with _state.flagged={sorted(mstubs)}")

    # --- Test 3b: orig-side keys resolve against live orig codings ---
    resolved = sum(1 for p in contrast + noncorrect if p["orig_key"] in mvalid)
    print(f"INFO: {resolved}/80 orig-side flip keys resolve against partial minimax orig codings")

    print("\nALL SELF-TESTS PASSED")
    return 0


def build_parser():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--census-dir", default=DEFAULTS["census_dir"])
    ap.add_argument("--coders", default=None,
                    help="comma list; default auto-detect subdirs with codings")
    ap.add_argument("--records", default=DEFAULTS["records"])
    ap.add_argument("--mechanisms", default=DEFAULTS["mechanisms"])
    ap.add_argument("--errors", default=DEFAULTS["errors"])
    ap.add_argument("--orig-db", default=DEFAULTS["orig_db"])
    ap.add_argument("--rerun-db", default=DEFAULTS["rerun_db"])
    ap.add_argument("--set", choices=("orig", "rerun_divergent", "all"), default="all")
    ap.add_argument("--outdir", default=None,
                    help="default: <census-dir>/analysis")
    ap.add_argument("--sample-n", type=int, default=40, help="0 = skip sanity dump")
    ap.add_argument("--seed", type=int, default=20260701)
    ap.add_argument("--trace-dir", default=DEFAULTS["trace_dir"],
                    help="read-only dir with <set>/<trace_id>.md for the sanity dump")
    ap.add_argument("--nc-basis", choices=("wrong-only", "wrong-plus-abstained"),
                    default="wrong-only",
                    help="decision (a): peel chain base. wrong-only (default) reports "
                         "abstained as its own outcome; wrong-plus-abstained folds it in.")
    ap.add_argument("--strict", action="store_true",
                    help="raise on stub/flagged reconciliation mismatch")
    ap.add_argument("--self-test", action="store_true",
                    help="run unit fixtures (no writes) and exit")
    return ap


def main(argv=None):
    args = build_parser().parse_args(argv)
    if args.outdir is None:
        args.outdir = os.path.join(args.census_dir, "analysis")
    if args.self_test:
        return self_test(args)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
