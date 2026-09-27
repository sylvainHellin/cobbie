# /// script
# requires-python = ">=3.10"
# dependencies = ["langchain", "langchain-anthropic", "python-dotenv", "httpx"]
# ///
"""Stage 2 of the coding pipeline: closed-coding census runner.

Re-codes ALL 594 traces (from ``_consolidation_records.json``) against the
FROZEN controlled vocabularies (``codebook/{mechanisms,errors}.frozen.json``),
once per backbone. Unlike induction (Stage 1, which clustered the pooled open
codes and never re-read a trace), the census codes against the FULL
reconstructed agent trace -- the same substrate the Stage-0 open-coders saw:
system prompt -> question -> every CodeAct step (generated_code + observation)
-> final predicted answer -> ground truth -> judge verdict/justification. The
trace is reassembled verbatim via ``build_trace_history.render_trace_block``.

Two backbones ARE the two independent coders (Gate C [D-census]); each runs as a
SEPARATE job and writes to its own per-backbone/per-set output. The taxonomy
(ids, definitions, scope_note, other_rule, track) is loaded from the frozen JSON
at runtime -- never hard-coded -- so the prompt and the validator stay in lock
step with the freeze.

Coding rules (baked into the prompt AND enforced by this driver):
  * mechanisms (M1-M10 + M-Other) coded on EVERY trace;
  * errors (E1,E2,E4a,E4b,E4c,E-Other agent + E7,E14 non-agent) coded ONLY when
    verdict in {wrong, abstained}; on ``correct`` traces error_ids MUST be [];
  * only listed ids may be assigned (closed coding); M-Other/E-Other are the sole
    escape hatches and REQUIRE a non-empty free-text named-pattern note.

Backbone dispatch (the one real branch):
  * ``glm:glm-5.2``            -> IPv4-pinned httpx clients (the v6 route to
    api.z.ai is a blackhole on this host) + request_timeout; within-backbone
    concurrency stays SEQUENTIAL (z.ai throttles -- never fan out glm).
  * ``minimax-anthropic:MiniMax-M3`` -> Anthropic path (ChatAnthropic), NO IPv4
    pin, NO http_client. init_llm maps request_timeout -> ``timeout`` for this
    path, so a 600s ceiling reaches ChatAnthropic unchanged.

Output layout (sets kept strictly separate, per backbone, keyed by trace_id):
    outputs/analysis/census_20260701/
      <backbone-slug>/
        orig.codings.json            # { trace_id: {verdict, mechanism_ids, ...} }
        rerun_divergent.codings.json
        _state.json                  # {backbone, sets:{set:{done:[...], next_idx}}}
Checkpoint after EVERY trace so --resume re-runs only the uncoded tail. On a
JSON-parse or validation failure the raw response is recorded and the run
continues; the trace is flagged for a repair pass.

Usage:
    uv run python scripts/classify_census.py --backbone glm:glm-5.2 --dry-run
    uv run python scripts/classify_census.py --backbone minimax-anthropic:MiniMax-M3
    uv run python scripts/classify_census.py --backbone glm:glm-5.2 --resume

All input sqlite/records/frozen files are READ-ONLY (sqlite via ?mode=ro); the
script writes ONLY under --outdir.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_THIS_DIR)
for _p in (_ROOT, _THIS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Reuse the induction plumbing (IPv4 clients, retry envelope + constants, robust
# JSON parse) and the canonical trace reconstruction verbatim.
from induce_codebook import (  # noqa: E402
    _ipv4_http_clients,
    _retryable_excs,
    _is_rate_limit,
    robust_load,
    _RETRY_MAX_ATTEMPTS,
    _RETRY_BASE_S,
    _RETRY_CEILING_S,
    _RATE_LIMIT_SLEEP_S,
    _REQUEST_TIMEOUT_S,
)
from build_trace_history import (  # noqa: E402
    render_trace_block,
    load_run_metadata,
    load_result_row,
    load_steps,
    load_question_index,
    assemble_prompt,
    TRACE_TOKEN,
)

DEFAULT_RECORDS = "outputs/analysis/opencoding_full_20260626/_consolidation_records.json"
DEFAULT_MECHANISMS = "outputs/analysis/opencoding_full_20260626/codebook/mechanisms.frozen.json"
DEFAULT_ERRORS = "outputs/analysis/opencoding_full_20260626/codebook/errors.frozen.json"
DEFAULT_PROMPT = "prompts/classify_census.md"
DEFAULT_OUTDIR = "outputs/analysis/census_20260701"

# set -> the frozen results.sqlite that holds that set's transcripts. Keyed by
# the record's `set` field (NOT cell_id -- both sets carry the identical cell_id
# "minimax-m3__agentic__none").
SET_DB = {
    "orig": "outputs/factorial/minimax-m3__agentic__none/results.sqlite",
    "rerun_divergent": "outputs/factorial_rerun_20260624/minimax-m3__agentic__none/results.sqlite",
}
SETS = ("orig", "rerun_divergent")

# Verdicts that additionally get error coding. correct traces get mechanisms only.
ERROR_VERDICTS = {"wrong", "abstained"}

_TRACE_ID_RE = re.compile(r"q(\d+)_r(\d+)_(\w+)")


# --------------------------------------------------------------------------- #
# Frozen vocabulary
# --------------------------------------------------------------------------- #
def load_vocab(path: str) -> dict:
    """Load a frozen vocabulary JSON (scope_note, other_rule, categories)."""
    return json.load(open(path, encoding="utf-8"))


def allowed_ids(vocab: dict) -> list[str]:
    return [c["id"] for c in vocab["categories"]]


def other_id(vocab: dict) -> str | None:
    for cid in allowed_ids(vocab):
        if cid.endswith("-Other"):
            return cid
    return None


def render_categories(vocab: dict) -> str:
    """Render the frozen categories as a markdown bullet list for the prompt.

    Emits id, name, definition, and (when present) the error track so the coder
    sees the agent vs non-agent distinction. Rendered FROM the frozen JSON so it
    never drifts from the freeze.
    """
    lines = []
    for c in vocab["categories"]:
        track = c.get("track")
        track_tag = f" [track: {track}]" if track else ""
        lines.append(f"- **{c['id']}** — {c['name']}{track_tag}: {c['definition']}")
    return "\n".join(lines)


def render_prompt_template(template: str, mech: dict, err: dict) -> str:
    """Substitute the frozen vocab placeholders (leaves {{TRACE}} for per-trace)."""
    s = template
    s = s.replace("{{MECH_SCOPE_NOTE}}", mech.get("scope_note", "").strip())
    s = s.replace("{{MECH_OTHER_RULE}}", mech.get("other_rule", "").strip())
    s = s.replace("{{MECH_CATEGORIES}}", render_categories(mech))
    s = s.replace("{{ERR_SCOPE_NOTE}}", err.get("scope_note", "").strip())
    s = s.replace("{{ERR_OTHER_RULE}}", err.get("other_rule", "").strip())
    s = s.replace("{{ERR_CATEGORIES}}", render_categories(err))
    return s


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #
def load_records(path: str, which_set: str) -> list[dict]:
    recs = json.load(open(path, encoding="utf-8"))
    if which_set != "all":
        recs = [r for r in recs if r["set"] == which_set]
    recs.sort(key=lambda r: (r["set"], r["question_id"]))
    return recs


def parse_trace_id(trace_id: str) -> tuple[int, int, str]:
    m = _TRACE_ID_RE.match(trace_id)
    if not m:
        raise ValueError(f"unparseable trace_id: {trace_id!r}")
    return int(m.group(1)), int(m.group(2)), m.group(3)


# --------------------------------------------------------------------------- #
# Per-cell caches (open the sqlite read-only; load meta + question-index ONCE)
# --------------------------------------------------------------------------- #
class CellCache:
    """Lazily loads + caches run_metadata and the judge-batch question index for
    one set's sqlite cell. question_index scans every judge batch, so it is
    loaded exactly once per cell."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._meta = None
        self._qindex = None

    @property
    def meta(self) -> dict:
        if self._meta is None:
            self._meta = load_run_metadata(self.db_path)
        return self._meta

    @property
    def qindex(self) -> dict:
        if self._qindex is None:
            self._qindex = load_question_index(self.db_path)
        return self._qindex


def build_trace_prompt(cell: CellCache, template: str, trace_id: str,
                       obs_cap: int, sysprompt_cap: int) -> tuple[str, dict]:
    """Reconstruct one trace and substitute it into the closed-coding prompt.

    Returns (prompt, info) where info flags whether the question/ground-truth
    lookup was resolved (missing => a WARN-worthy degraded trace)."""
    qid, ridx, _verdict = parse_trace_id(trace_id)
    row = load_result_row(cell.db_path, qid, ridx)
    if not row:
        raise LookupError(f"no results row for {trace_id} (q{qid} r{ridx})")
    ridx_actual = row["repeat_idx"]
    steps = load_steps(cell.db_path, qid, ridx_actual)
    cell_id = cell.meta.get("cell_id")
    info = cell.qindex.get((cell_id, qid, ridx_actual))
    q_resolved = info is not None
    if info is None:
        info = {
            "question": "_(question unavailable: no judge-batch entry)_",
            "ground_truth": "_(reference unavailable: no judge-batch entry)_",
        }
    block = render_trace_block(cell.meta, info, row, steps, obs_cap, sysprompt_cap)
    prompt = assemble_prompt(block, template)
    meta = {
        "question_id": qid,
        "repeat_idx": ridx_actual,
        "header_verdict": (row.get("classification") or "unknown").lower(),
        "num_steps": len(steps),
        "question_resolved": q_resolved,
    }
    return prompt, meta


# --------------------------------------------------------------------------- #
# Validation of the model's coding against the frozen whitelist + gates
# --------------------------------------------------------------------------- #
class CodingError(ValueError):
    """A coding that violates the closed-coding contract (rejected -> flagged)."""


def _as_id_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        raise CodingError(f"expected a list of ids, got {type(value).__name__}")
    out = []
    for v in value:
        if not isinstance(v, str):
            raise CodingError(f"non-string id in list: {v!r}")
        v = v.strip()
        if v:
            out.append(v)
    # de-dup, preserve order
    seen = set()
    uniq = []
    for v in out:
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    return uniq


def validate_coding(raw: dict, trace_id: str, header_verdict: str,
                    mech_vocab: dict, err_vocab: dict) -> dict:
    """Normalize + validate a parsed coding. Raises CodingError on a violation
    that should flag the trace for a repair pass. Deterministic driver-owned
    fixes (empty error list on correct traces) are applied silently."""
    mech_allowed = set(allowed_ids(mech_vocab))
    err_allowed = set(allowed_ids(err_vocab))
    mech_other = other_id(mech_vocab)   # "M-Other"
    err_other = other_id(err_vocab)     # "E-Other"

    mechanism_ids = _as_id_list(raw.get("mechanism_ids"))
    error_ids = _as_id_list(raw.get("error_ids"))
    mech_note = raw.get("mechanism_other_note")
    err_note = raw.get("error_other_note")
    evidence = raw.get("evidence") or {}
    if not isinstance(evidence, dict):
        raise CodingError("`evidence` must be an object mapping id -> justification")

    # 1. Whitelist enforcement (closed coding: only listed ids).
    bad_m = [m for m in mechanism_ids if m not in mech_allowed]
    if bad_m:
        raise CodingError(f"mechanism_ids not in frozen vocab: {bad_m}")
    bad_e = [e for e in error_ids if e not in err_allowed]
    if bad_e:
        raise CodingError(f"error_ids not in frozen vocab: {bad_e}")

    # 2. Error gate: errors only on wrong/abstained; force [] on correct.
    if header_verdict not in ERROR_VERDICTS:
        error_ids = []
        err_note = None

    # 3. Other-note enforcement (the sole escape hatches require a named pattern).
    if mech_other and mech_other in mechanism_ids:
        if not (isinstance(mech_note, str) and mech_note.strip()):
            raise CodingError(f"{mech_other} requires a non-empty mechanism_other_note")
    else:
        mech_note = mech_note if (isinstance(mech_note, str) and mech_note.strip()) else None
    if err_other and err_other in error_ids:
        if not (isinstance(err_note, str) and err_note.strip()):
            raise CodingError(f"{err_other} requires a non-empty error_other_note")
    else:
        err_note = err_note if (isinstance(err_note, str) and err_note.strip()) else None

    return {
        "trace_id": trace_id,
        "verdict": header_verdict,
        "mechanism_ids": mechanism_ids,
        "error_ids": error_ids,
        "mechanism_other_note": mech_note.strip() if isinstance(mech_note, str) else None,
        "error_other_note": err_note.strip() if isinstance(err_note, str) else None,
        "evidence": {str(k): v for k, v in evidence.items()},
    }


# --------------------------------------------------------------------------- #
# LLM: backbone dispatch + retry envelope
# --------------------------------------------------------------------------- #
def build_llm(backbone: str):
    """Init the coder LLM with the correct provider plumbing.

    glm -> IPv4-pinned httpx clients + request_timeout (z.ai v6 blackhole);
    minimax-anthropic -> Anthropic path, NO IPv4 pin / NO http_client. init_llm
    maps request_timeout -> `timeout` on the Anthropic path, so the 600s ceiling
    reaches ChatAnthropic unchanged (verified: src/harness/llm.py setdefault)."""
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.getcwd(), ".env"))
    from src.harness.llm import init_llm

    prefix = backbone.split(":", 1)[0]
    if prefix == "glm":
        http_client, http_async_client = _ipv4_http_clients()
        llm = init_llm(backbone, temperature=0, request_timeout=_REQUEST_TIMEOUT_S,
                       http_client=http_client, http_async_client=http_async_client)
    elif prefix == "minimax-anthropic":
        # NO IPv4 pin, NO http_client (api.minimax.io is a normal route; the
        # ChatAnthropic client takes `timeout`, which init_llm derives from
        # request_timeout).
        llm = init_llm(backbone, temperature=0, request_timeout=_REQUEST_TIMEOUT_S)
    else:
        raise SystemExit(f"unsupported backbone: {backbone!r} "
                         "(expected glm:... or minimax-anthropic:...)")
    return llm


def make_caller(llm):
    """Build a retry-wrapped, synchronous `call(prompt) -> raw_text`.

    Mirrors induce_codebook.call(): bounded exp backoff (1/2/4/8s) on transient
    connect/TLS/timeout faults; 429/quota -> a single longer sleep (30s) so we
    never retry-storm a real rate limit. SEQUENTIAL by construction (one call at
    a time) -- glm must never be fanned out."""
    retryable = _retryable_excs()

    def call(prompt: str) -> str:
        attempt = 0
        while True:
            try:
                resp = llm.invoke(prompt).content
                return resp if isinstance(resp, str) else _flatten(resp)
            except retryable as exc:
                if attempt >= _RETRY_MAX_ATTEMPTS - 1:
                    raise
                wait = min(_RETRY_BASE_S * (2 ** attempt), _RETRY_CEILING_S)
                print(f"    [retry] transient network error "
                      f"({type(exc).__name__}: {exc}); attempt "
                      f"{attempt + 1}/{_RETRY_MAX_ATTEMPTS}, sleeping {wait:.1f}s",
                      flush=True)
                time.sleep(wait)
                attempt += 1
            except Exception as exc:  # noqa: BLE001
                if _is_rate_limit(exc) and attempt < _RETRY_MAX_ATTEMPTS - 1:
                    print(f"    [backoff] rate limit ({type(exc).__name__}); "
                          f"sleeping {_RATE_LIMIT_SLEEP_S:.0f}s", flush=True)
                    time.sleep(_RATE_LIMIT_SLEEP_S)
                    attempt += 1
                    continue
                raise

    return call


def _flatten(content) -> str:
    if isinstance(content, list):  # some providers return content blocks
        return "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in content
        )
    return str(content)


# --------------------------------------------------------------------------- #
# Output + checkpoint
# --------------------------------------------------------------------------- #
def _codings_path(backbone_dir: str, which_set: str) -> str:
    return os.path.join(backbone_dir, f"{which_set}.codings.json")


def _state_path(backbone_dir: str) -> str:
    return os.path.join(backbone_dir, "_state.json")


def load_codings(backbone_dir: str, which_set: str) -> dict:
    path = _codings_path(backbone_dir, which_set)
    if os.path.isfile(path):
        return json.load(open(path, encoding="utf-8"))
    return {}


def write_codings(backbone_dir: str, which_set: str, codings: dict):
    path = _codings_path(backbone_dir, which_set)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(codings, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def write_state(backbone_dir: str, state: dict):
    path = _state_path(backbone_dir)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# --------------------------------------------------------------------------- #
# Dry-run
# --------------------------------------------------------------------------- #
def dry_run(backbone_dir: str, template: str, records: list[dict], args):
    """Render ONE fully-substituted trace prompt (vocab + reconstructed trace),
    make ZERO API calls, write it under the backbone dir, and print an excerpt."""
    rec = records[0]
    which_set = rec["set"]
    cell = CellCache(SET_DB[which_set])
    prompt, meta = build_trace_prompt(cell, template, rec["trace_id"],
                                      args.obs_cap, args.sysprompt_cap)
    os.makedirs(backbone_dir, exist_ok=True)
    path = os.path.join(backbone_dir, "_dry_run_preview.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(prompt)
    lines = prompt.splitlines()
    print(f"DRY-RUN [{args.backbone}] trace_id={rec['trace_id']} set={which_set} "
          f"verdict={meta['header_verdict']} steps={meta['num_steps']} "
          f"question_resolved={meta['question_resolved']}", flush=True)
    print(f"DRY-RUN: wrote fully-substituted prompt -> {path} "
          f"({len(prompt)} chars, {len(lines)} lines)", flush=True)
    print("DRY-RUN: TRACE token substituted:", TRACE_TOKEN not in prompt, flush=True)
    print("----- first 40 lines -----", flush=True)
    print("\n".join(lines[:40]), flush=True)
    print("----- last 15 lines -----", flush=True)
    print("\n".join(lines[-15:]), flush=True)
    print("DRY-RUN: zero API calls made.", flush=True)


# --------------------------------------------------------------------------- #
# Live run (one set)
# --------------------------------------------------------------------------- #
def run_set(backbone_dir: str, template: str, records: list[dict], which_set: str,
            call, state: dict, args) -> None:
    cell = CellCache(SET_DB[which_set])
    codings = load_codings(backbone_dir, which_set)
    sstate = state["sets"].setdefault(which_set, {"done": [], "next_idx": 0})
    done = set(sstate["done"])
    flagged = set(sstate.get("flagged", []))

    todo = [r for r in records if r["set"] == which_set]
    if args.max_traces is not None:
        todo = todo[:args.max_traces]

    total = len(todo)
    coded = 0
    for i, rec in enumerate(todo):
        trace_id = rec["trace_id"]
        if trace_id in done:
            continue
        try:
            prompt, meta = build_trace_prompt(cell, template, trace_id,
                                              args.obs_cap, args.sysprompt_cap)
        except (LookupError, ValueError) as exc:
            print(f"  [{which_set} {i+1}/{total}] {trace_id}: SKIP-UNRESOLVABLE "
                  f"({exc})", file=sys.stderr, flush=True)
            codings[trace_id] = {"trace_id": trace_id, "_error": f"unresolvable: {exc}"}
            flagged.add(trace_id)
            done.add(trace_id)
            _checkpoint(backbone_dir, which_set, codings, sstate, done, flagged,
                        i + 1, state)
            continue

        if not meta["question_resolved"]:
            print(f"  [{which_set} {i+1}/{total}] {trace_id}: WARN no judge-batch "
                  f"question/ground-truth (degraded trace)", file=sys.stderr, flush=True)

        try:
            raw = call(prompt)
        except Exception as exc:  # noqa: BLE001
            # A hard call failure after the retry envelope is exhausted: leave
            # the trace UNCODED (not in done) so --resume retries it, checkpoint
            # the tail we have, and stop this set cleanly.
            print(f"  [{which_set} {i+1}/{total}] {trace_id}: CALL FAILED "
                  f"({type(exc).__name__}: {exc}); checkpoint intact, resume to "
                  f"retry.", file=sys.stderr, flush=True)
            _checkpoint(backbone_dir, which_set, codings, sstate, done, flagged,
                        i, state)
            raise

        entry, ok = _parse_and_validate(raw, trace_id, meta["header_verdict"],
                                        args._mech_vocab, args._err_vocab)
        codings[trace_id] = entry
        done.add(trace_id)
        if not ok:
            flagged.add(trace_id)
            print(f"  [{which_set} {i+1}/{total}] {trace_id}: FLAGGED "
                  f"({entry.get('_error')})", file=sys.stderr, flush=True)
        else:
            coded += 1
            print(f"  [{which_set} {i+1}/{total}] {trace_id} [{entry['verdict']}] "
                  f"M={entry['mechanism_ids']} E={entry['error_ids']}", flush=True)
        _checkpoint(backbone_dir, which_set, codings, sstate, done, flagged,
                    i + 1, state)

    print(f"[{which_set}] done: {coded} newly coded, {len(flagged)} flagged, "
          f"{len(done)} total in done-set.", flush=True)


def _parse_and_validate(raw: str, trace_id: str, header_verdict: str,
                        mech_vocab: dict, err_vocab: dict) -> tuple[dict, bool]:
    try:
        parsed = robust_load(raw)
    except Exception as exc:  # noqa: BLE001
        return ({"trace_id": trace_id, "verdict": header_verdict,
                 "_error": f"json-parse: {type(exc).__name__}: {exc}",
                 "raw_response": raw}, False)
    try:
        entry = validate_coding(parsed, trace_id, header_verdict, mech_vocab, err_vocab)
        return entry, True
    except CodingError as exc:
        return ({"trace_id": trace_id, "verdict": header_verdict,
                 "_error": f"validation: {exc}", "raw_response": raw,
                 "raw_parsed": parsed}, False)


def _checkpoint(backbone_dir: str, which_set: str, codings: dict, sstate: dict,
                done: set, flagged: set, next_idx: int, state: dict):
    # Checkpoint after EVERY trace: persist BOTH the codings and the full state
    # file so --resume re-runs only the uncoded tail. sstate is a live sub-dict
    # of state["sets"][which_set], so mutating it updates `state` in place.
    sstate["done"] = sorted(done)
    sstate["flagged"] = sorted(flagged)
    sstate["next_idx"] = next_idx
    write_codings(backbone_dir, which_set, codings)
    write_state(backbone_dir, state)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def slug_for(backbone: str) -> str:
    name = backbone.split(":", 1)[1] if ":" in backbone else backbone
    return name.lower()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backbone", required=True,
                    help="coder LLM: glm:glm-5.2 or minimax-anthropic:MiniMax-M3")
    ap.add_argument("--set", default="all", choices=["orig", "rerun_divergent", "all"],
                    help="trace set(s) to code (default all; sets kept separate)")
    ap.add_argument("--records", default=DEFAULT_RECORDS)
    ap.add_argument("--mechanisms", default=DEFAULT_MECHANISMS)
    ap.add_argument("--errors", default=DEFAULT_ERRORS)
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    ap.add_argument("--outdir", default=DEFAULT_OUTDIR)
    ap.add_argument("--parallel", type=int, default=1,
                    help="accepted for parity; the per-trace loop is SEQUENTIAL "
                         "(glm must never be fanned out). Default 1.")
    ap.add_argument("--obs-cap", type=int, default=2000,
                    help="chars per observation (matches Stage-0 open coding)")
    ap.add_argument("--sysprompt-cap", type=int, default=0,
                    help="chars for the system prompt (0 = full, no truncation)")
    ap.add_argument("--max-traces", type=int, default=None,
                    help="optional cap per set (smoke test)")
    ap.add_argument("--resume", action="store_true",
                    help="resume from <outdir>/<slug>/_state.json (skip done ids)")
    ap.add_argument("--fresh", action="store_true",
                    help="start over, overwriting any existing checkpoint")
    ap.add_argument("--dry-run", action="store_true",
                    help="render ONE fully-substituted trace prompt; ZERO API calls")
    args = ap.parse_args(argv)

    if args.resume and args.fresh:
        print("error: pass only one of --resume / --fresh", file=sys.stderr)
        return 2
    for p in (args.records, args.mechanisms, args.errors, args.prompt):
        if not os.path.isfile(p):
            print(f"error: not found: {p}", file=sys.stderr)
            return 2

    mech_vocab = load_vocab(args.mechanisms)
    err_vocab = load_vocab(args.errors)
    args._mech_vocab = mech_vocab
    args._err_vocab = err_vocab

    raw_template = open(args.prompt, encoding="utf-8").read()
    template = render_prompt_template(raw_template, mech_vocab, err_vocab)
    if TRACE_TOKEN not in template:
        print(f"error: prompt {args.prompt} is missing the {TRACE_TOKEN} token",
              file=sys.stderr)
        return 2

    records = load_records(args.records, args.set)
    if not records:
        print(f"error: no records for set={args.set}", file=sys.stderr)
        return 2

    slug = slug_for(args.backbone)
    backbone_dir = os.path.join(args.outdir, slug)
    sel_sets = SETS if args.set == "all" else (args.set,)

    if args.dry_run:
        dry_run(backbone_dir, template, records, args)
        return 0

    state_path = _state_path(backbone_dir)
    if (os.path.isfile(state_path) and not args.resume and not args.fresh):
        print(f"error: checkpoint exists at {state_path}; pass --resume to "
              f"continue or --fresh to start over", file=sys.stderr)
        return 2

    os.makedirs(backbone_dir, exist_ok=True)
    if args.resume and os.path.isfile(state_path):
        state = json.load(open(state_path, encoding="utf-8"))
        state.setdefault("sets", {})
        print(f"resumed state: "
              + ", ".join(f"{s}={len(state['sets'].get(s, {}).get('done', []))} done"
                          for s in sel_sets), flush=True)
    else:
        state = {"backbone": args.backbone, "slug": slug, "sets": {}}
        # --fresh over an existing set: clear its codings too.
        if args.fresh:
            for s in sel_sets:
                cp = _codings_path(backbone_dir, s)
                if os.path.isfile(cp):
                    os.remove(cp)

    counts = {}
    for s in sel_sets:
        counts[s] = sum(1 for r in records if r["set"] == s)
    print(f"backbone={args.backbone} slug={slug} sets={sel_sets} "
          f"counts={counts}", flush=True)

    llm = build_llm(args.backbone)
    call = make_caller(llm)

    for s in sel_sets:
        run_set(backbone_dir, template, records, s, call, state, args)
        write_state(backbone_dir, state)  # persist after each set completes

    # Ensure a final state flush.
    write_state(backbone_dir, state)
    print("CENSUS COMPLETE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
