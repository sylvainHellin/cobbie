# /// script
# requires-python = ">=3.10"
# dependencies = ["langchain", "python-dotenv"]
# ///
"""Stage 1 of the open-coding consolidation pipeline: codebook induction.

Constant-comparative axial coding over the POOLED open codes (minimax + claude)
produced by Stage 0 (``consolidate_opencoding.py``) -- NOT a re-read of the
traces. Induces two parallel controlled vocabularies that share one batch
traversal:

  * mechanisms (RQ2) -- present on every trace,
  * errors (RQ3)     -- present only on wrong/abstained traces.

The LLM (``glm:glm-5.2``, temp 0) is STATELESS per batch: all vocabulary state
lives in JSON owned by this driver (reproducible, resumable, skip-existing). The
LLM only *proposes* (assignment of each open code to active/buffer/new, and merge
groups); the driver *executes* set operations (support unions, promotions,
merges) deterministically.

Two tiers (the convergence mechanism that bounds the active set):
  * ``active`` -- the controlled vocabulary, hard-bounded (~10 working). Seeds
    (``codebook/{mechanisms,errors}.seed.json``) pre-load it as a warm start.
  * ``buffer`` -- candidate phrasings awaiting recurrence
    ``{phrasing, definition, occurrences, trace_ids}``.

Per batch (default 5 traces, both coders' codes pooled):
  1. ASSIGNMENT call: map each open code -> an active category (preferred), an
     existing buffer candidate, or a NEW buffer candidate. The LLM may NOT mint
     active categories.
  2. Driver updates ``support`` (active: a set of distinct trace_ids, never
     double-counted) / ``occurrences`` + trace_ids (buffer).
  3. Consolidation (every batch): PROMOTE a buffer candidate that recurs in
     >= ``--promote-min`` distinct traces; run the MERGE call and EXECUTE the
     approved merges deterministically (keep absorbs dropped trace_ids by union,
     aliases, exemplars; dropped -> ``status: merged_into:<keep>``; provenance
     concatenated).

Stop on saturation: no promotions across 3 consecutive consolidations.

Outputs (under ``<indir>/codebook/``):
  * ``mechanisms.candidate.json`` / ``errors.candidate.json``
  * ``proposed_codebook.md``  (name, definition, support, ranked exemplars,
    aliases, provenance per category)
  * ``saturation_log.jsonl``  (one line per consolidation)
  * ``_induction_state.json`` (checkpoint after every batch, for resume)

``--dry-run`` builds the seeds + the FIRST batch, renders the fully-substituted
ASSIGNMENT and MERGE prompts with REAL batch-1 data to
``codebook/_prompt_preview_batch1.md``, and makes NO API call. The live run path
exists but is only entered without ``--dry-run``.

Usage:
    uv run python scripts/induce_codebook.py --dry-run        # offline preview
    uv run python scripts/induce_codebook.py                  # live run (API)

The records, seeds, and prompt template are read-only; the script only writes
the artifacts under ``codebook/``.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import date, datetime

DEFAULT_INDIR = "outputs/analysis/opencoding_full_20260626"
DEFAULT_RECORDS = "_consolidation_records.json"
DEFAULT_PROMPT = "prompts/induce_codebook.md"
CODEBOOK_SUBDIR = "codebook"
SEED_FILES = {"mechanisms": "mechanisms.seed.json", "errors": "errors.seed.json"}
VOCABS = ("mechanisms", "errors")
CODERS = ("minimax", "claude")
MODEL = "glm:glm-5.2"
ID_PREFIX = {"mechanisms": "M", "errors": "E"}
MAX_EXEMPLARS = 5
SAMPLE_ALIASES = 6
SATURATION_STOP = 3  # consecutive promotion-free consolidations

# Bounded retry envelope for transient network faults on THIS host's path to
# api.z.ai. Rationale: the v6 Tailscale route to z.ai is a blackhole, so the GLM
# client is pinned to IPv4 (see _ipv4_http_clients); IPv4 works once the NIC MTU
# (1492 at runtime) clears the PMTU blackhole, but the route still throws an
# occasional transient TLS-handshake reset / connection drop that succeeds on
# immediate retry. We retry connect/TLS/timeout errors with exponential backoff
# (1s,2s,4s) and treat 429/quota as a longer, separate sleep so we never
# retry-storm. Mirrors the backoff intent of scripts/run_cell.py:_run_with_backoff.
_RETRY_MAX_ATTEMPTS = 4
_RETRY_BASE_S = 1.0
_RETRY_CEILING_S = 8.0
_RATE_LIMIT_SLEEP_S = 30.0
# glm-5.2 is a reasoning model: a single assignment/merge call emits ~12k
# completion tokens (~7.5k reasoning) and takes ~3-4 min, so the 120s default
# would spuriously time out a healthy request. Give the request a generous
# ceiling on BOTH the httpx client and the openai request_timeout.
_REQUEST_TIMEOUT_S = 600.0


# --------------------------------------------------------------------------- #
# IPv4-pinned HTTP clients + transient-fault retry for the GLM/Z.AI endpoint
# --------------------------------------------------------------------------- #
def _ipv4_http_clients():
    """Build sync+async httpx clients pinned to IPv4 for api.z.ai.

    Rationale (this host): api.z.ai over IPv6 is a broken Tailscale route that
    times out; over IPv4 it works once the NIC MTU (1492, set at runtime) clears
    the PMTU blackhole so large POSTs return HTTP 200. Binding the transport's
    ``local_address="0.0.0.0"`` forces the OpenAI-compatible client onto IPv4
    instead of hanging on the dead v6 path. Both variants are built because
    ChatOpenAI keeps sync/async clients separate; induction only calls
    ``.invoke()`` (sync), but we wire both for safety.
    """
    import httpx
    timeout = httpx.Timeout(_REQUEST_TIMEOUT_S)
    sync = httpx.Client(
        transport=httpx.HTTPTransport(local_address="0.0.0.0"),
        timeout=timeout,
    )
    aclient = httpx.AsyncClient(
        transport=httpx.AsyncHTTPTransport(local_address="0.0.0.0"),
        timeout=timeout,
    )
    return sync, aclient


def _retryable_excs() -> tuple:
    """Transient connection/TLS/timeout exceptions worth an immediate retry."""
    import httpx
    excs = [
        httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout,
        httpx.WriteTimeout, httpx.PoolTimeout, httpx.RemoteProtocolError,
        httpx.ReadError, httpx.WriteError,
    ]
    try:
        import openai
        excs += [openai.APIConnectionError, openai.APITimeoutError]
    except Exception:
        pass
    return tuple(excs)


def _is_rate_limit(exc: BaseException) -> bool:
    text = f"{type(exc).__name__} {exc}".lower()
    return any(m in text for m in (
        "429", "rate limit", "rate_limit", "too many requests", "quota"))


# --------------------------------------------------------------------------- #
# Robust JSON extraction (mirrors consolidate_opencoding.py)
# --------------------------------------------------------------------------- #
def extract_json(raw: str) -> str:
    """Pull the JSON object out of a model response (fence + outermost braces)."""
    s = raw.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL)
    if m:
        s = m.group(1).strip()
    if "{" in s and not s.startswith("{"):
        s = s[s.find("{"):]
    if "}" in s and not s.endswith("}"):
        s = s[: s.rfind("}") + 1]
    return s.strip()


def robust_load(raw: str) -> dict:
    """Parse an LLM JSON response, raising on a genuinely unrecoverable body."""
    s = extract_json(raw)
    return json.loads(s)


# --------------------------------------------------------------------------- #
# Prompt template handling
# --------------------------------------------------------------------------- #
def load_template(path: str) -> dict[str, str]:
    """Split the template into its ASSIGNMENT and MERGE call sections."""
    text = open(path, encoding="utf-8").read()
    parts = re.split(r"\n-{3,}\n", text)
    sections = {"_context": parts[0]}
    for part in parts[1:]:
        head = part[:200]
        if "ASSIGNMENT" in head:
            sections["assignment"] = part.strip()
        elif "MERGE" in head:
            sections["merge"] = part.strip()
    if "assignment" not in sections or "merge" not in sections:
        raise ValueError(f"could not parse ASSIGNMENT/MERGE sections from {path}")
    return sections


def render_assignment(sections: dict, vocab: str, n_traces: int,
                      active_vocab_json: str, buffer_json: str,
                      batch_codes_json: str) -> str:
    s = sections["assignment"]
    s = s.replace("{{N_TRACES}}", str(n_traces))
    s = s.replace("{{VOCAB}}", vocab)
    s = s.replace("{{ACTIVE_VOCAB_JSON}}", active_vocab_json)
    s = s.replace("{{BUFFER_JSON}}", buffer_json)
    s = s.replace("{{BATCH_CODES_JSON}}", batch_codes_json)
    return s


def render_merge(sections: dict, vocab: str, active_vocab_json: str) -> str:
    s = sections["merge"]
    s = s.replace("{{VOCAB}}", vocab)
    s = s.replace("{{ACTIVE_VOCAB_JSON}}", active_vocab_json)
    return s


# --------------------------------------------------------------------------- #
# State: seeds, active/buffer records
# --------------------------------------------------------------------------- #
def load_seeds(codebook_dir: str) -> dict[str, dict]:
    """Load seed categories into an ``active`` warm start per vocabulary."""
    vstate: dict[str, dict] = {}
    for vocab in VOCABS:
        path = os.path.join(codebook_dir, SEED_FILES[vocab])
        seeds = json.load(open(path, encoding="utf-8"))
        active: dict[str, dict] = {}
        for s in seeds:
            rec = {
                "id": s["id"],
                "name": s["name"],
                "definition": s["definition"],
                "provenance": s["provenance"],
                "aliases": list(s.get("aliases", [])),
                "trace_ids": [],            # set, serialized as sorted list
                "exemplars": [],
                "first_seen_batch": None,
                "last_seen_batch": None,
                "status": "active",
            }
            if "track" in s:
                rec["track"] = s["track"]
            # `umbrella` is driver/analysis-only metadata (Stage-3 reports the
            # umbrella's union prevalence + each sub-code separately). It rides
            # through to the active record / candidate.json but is deliberately
            # NOT emitted by active_for_prompt(), so the LLM never sees it.
            if "umbrella" in s:
                rec["umbrella"] = s["umbrella"]
            active[s["id"]] = rec
        vstate[vocab] = {"active": active, "buffer": {}, "next_buffer_n": 1,
                         "next_active_n": _next_n(active, ID_PREFIX[vocab])}
    return vstate


def _next_n(active: dict, prefix: str) -> int:
    nums = [int(m.group(1)) for k in active
            for m in [re.match(rf"{prefix}(\d+)$", k)] if m]
    return (max(nums) + 1) if nums else 1


def active_for_prompt(active: dict) -> list[dict]:
    out = []
    for rec in active.values():
        if rec["status"] != "active":
            continue
        out.append({
            "id": rec["id"],
            "name": rec["name"],
            "definition": rec["definition"],
            "sample_aliases": rec["aliases"][:SAMPLE_ALIASES],
        })
    return out


def active_for_merge_prompt(active: dict) -> list[dict]:
    """Active-vocab payload for the MERGE call (CALL B).

    Identical to active_for_prompt() but ALSO exposes the `umbrella` field so
    CALL B can honor the 'never merge two shared-umbrella siblings' rule (M1/M2/
    M3 are intentionally distinct sub-codes of the schema-structure-discovery
    umbrella). The ASSIGNMENT call (CALL A) deliberately keeps using
    active_for_prompt() so the coding LLM never sees umbrella at assignment time.
    Only emitted when non-null, so non-umbrella categories stay clean.
    """
    by_id = {rec["id"]: rec for rec in active.values()}
    out = active_for_prompt(active)
    for entry in out:
        umb = by_id[entry["id"]].get("umbrella")
        if umb:
            entry["umbrella"] = umb
    return out


def buffer_for_prompt(buffer: dict) -> list[dict]:
    return [{"id": rec["id"], "phrasing": rec["phrasing"],
             "occurrences": rec["occurrences"]} for rec in buffer.values()]


# --------------------------------------------------------------------------- #
# Records / batching
# --------------------------------------------------------------------------- #
def load_records(path: str, which_set: str) -> list[dict]:
    recs = json.load(open(path, encoding="utf-8"))
    if which_set == "all":
        sel = recs
    else:
        sel = [r for r in recs if r["set"] == which_set]
    sel.sort(key=lambda r: (r["set"], r["question_id"]))
    return sel


def pooled_codes(rec: dict, vocab: str) -> list[dict]:
    """Pool both coders' labels for one vocabulary on one trace.

    Returns a list of ``{label, evidence, coder}`` (coder kept for exemplars;
    stripped before the LLM sees it).
    """
    out = []
    for coder in CODERS:
        c = rec["coders"].get(coder)
        if not c:
            continue
        for it in c.get(vocab, []) or []:
            label = (it.get("label") or "").strip()
            if not label:
                continue
            out.append({"label": label,
                        "evidence": (it.get("evidence") or "").strip(),
                        "coder": coder})
    return out


def batch_codes_for_prompt(batch: list[dict], vocab: str) -> tuple[list[dict], dict]:
    """Build the LLM-facing batch payload + an internal (trace,label)->meta map."""
    payload = []
    lookup: dict[tuple, dict] = {}
    for rec in batch:
        codes = pooled_codes(rec, vocab)
        payload.append({
            "trace_id": rec["trace_id"],
            "verdict": rec["verdict"],
            vocab: [{"label": c["label"], "evidence": c["evidence"]} for c in codes],
        })
        for c in codes:
            lookup.setdefault((rec["trace_id"], c["label"]),
                              {"coder": c["coder"], "evidence": c["evidence"]})
    return payload, lookup


# --------------------------------------------------------------------------- #
# Driver updates (executed from LLM proposals)
# --------------------------------------------------------------------------- #
def _norm(s: str) -> str:
    """Conservative normalized key: lowercase, strip, collapse whitespace.

    Exact-normalized only (NOT fuzzy) so genuinely distinct concepts are never
    merged; used to dedup `new` decisions against existing buffer/active names.
    """
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _add_trace(rec: dict, trace_id: str):
    if trace_id not in rec["trace_ids"]:
        rec["trace_ids"].append(trace_id)


def _add_exemplar(rec: dict, trace_id: str, label: str, lookup: dict):
    meta = lookup.get((trace_id, label), {})
    ex = {"trace_id": trace_id, "coder": meta.get("coder"),
          "quote": meta.get("evidence", ""), "open_label": label}
    rec["exemplars"].append(ex)


def apply_assignments(vstate: dict, vocab: str, assignments: list[dict],
                      lookup: dict, batch_idx: int):
    active = vstate[vocab]["active"]
    buffer = vstate[vocab]["buffer"]
    for a in assignments:
        trace_id = a.get("trace_id")
        label = a.get("label", "")
        decision = (a.get("decision") or a.get("kind") or "").strip()
        target = a.get("target_id")
        if decision == "active" and target in active:
            rec = active[target]
            _add_trace(rec, trace_id)
            if label and label not in rec["aliases"]:
                rec["aliases"].append(label)
            _add_exemplar(rec, trace_id, label, lookup)
            # FIX: explicit None check -- `or` clobbers a legitimate batch 0.
            if rec["first_seen_batch"] is None:
                rec["first_seen_batch"] = batch_idx
            rec["last_seen_batch"] = batch_idx
        elif decision == "buffer" and target in buffer:
            rec = buffer[target]
            _add_trace(rec, trace_id)
            rec["occurrences"] += 1
            if label and label not in rec["aliases"]:
                rec["aliases"].append(label)
            _add_exemplar(rec, trace_id, label, lookup)
        else:  # new (or an unmatched target) -> stage a fresh buffer candidate
            # Dedup guard: the LLM sometimes emits `new` for a concept already
            # represented. Use a conservative exact-normalized name match (NOT
            # fuzzy) so we never create a duplicate buffer row / inflate the
            # recurrence gate, while keeping genuinely distinct concepts apart.
            concept = a.get("new_name") or label
            key = _norm(concept)
            existing_buf = next(
                (r for r in buffer.values() if _norm(r["phrasing"]) == key), None
            ) if key else None
            existing_active = next(
                (r for r in active.values()
                 if r["status"] == "active" and _norm(r["name"]) == key), None
            ) if (key and existing_buf is None) else None
            if existing_buf is not None:
                # Same candidate phrasing already buffered: count the recurrence.
                _add_trace(existing_buf, trace_id)
                existing_buf["occurrences"] += 1
                if label and label not in existing_buf["aliases"]:
                    existing_buf["aliases"].append(label)
                _add_exemplar(existing_buf, trace_id, label, lookup)
                continue
            if existing_active is not None:
                # Concept is already a promoted active category: route support
                # there instead of buffering a duplicate.
                _add_trace(existing_active, trace_id)
                if label and label not in existing_active["aliases"]:
                    existing_active["aliases"].append(label)
                _add_exemplar(existing_active, trace_id, label, lookup)
                if existing_active["first_seen_batch"] is None:
                    existing_active["first_seen_batch"] = batch_idx
                existing_active["last_seen_batch"] = batch_idx
                continue
            n = vstate[vocab]["next_buffer_n"]
            vstate[vocab]["next_buffer_n"] = n + 1
            bid = f"{ID_PREFIX[vocab]}buf{n}"
            buffer[bid] = {
                "id": bid,
                "phrasing": a.get("new_name") or label,
                "definition": a.get("new_definition", ""),
                "occurrences": 1,
                "trace_ids": [trace_id],
                "aliases": [label] if label else [],
                "exemplars": [],
                "first_seen_batch": batch_idx,
            }
            _add_exemplar(buffer[bid], trace_id, label, lookup)


def promote(vstate: dict, vocab: str, promote_min: int, batch_idx: int) -> list[str]:
    """Promote buffer candidates recurring in >= promote_min distinct traces.

    Assignment-time routing already folds rephrasings of an active category onto
    that category, so a surviving buffer candidate is by construction not a
    rephrasing of an active one; recurrence is the promotion gate.
    """
    active = vstate[vocab]["active"]
    buffer = vstate[vocab]["buffer"]
    promoted = []
    for bid in list(buffer):
        cand = buffer[bid]
        if len(cand["trace_ids"]) < promote_min:
            continue
        n = vstate[vocab]["next_active_n"]
        vstate[vocab]["next_active_n"] = n + 1
        aid = f"{ID_PREFIX[vocab]}{n}"
        active[aid] = {
            "id": aid,
            "name": cand["phrasing"],
            "definition": cand["definition"],
            "provenance": "emergent",
            "aliases": list(cand["aliases"]),
            "trace_ids": list(cand["trace_ids"]),
            "exemplars": list(cand["exemplars"]),
            "first_seen_batch": cand["first_seen_batch"],
            "last_seen_batch": batch_idx,
            "status": "active",
        }
        del buffer[bid]
        promoted.append(aid)
    return promoted


def execute_merges(vstate: dict, vocab: str, merges: list[dict]) -> list[dict]:
    """Deterministically execute LLM-proposed merges (set-union absorption)."""
    active = vstate[vocab]["active"]
    done = []
    for mg in merges:
        keep_id = mg.get("keep_id")
        drop_ids = [d for d in (mg.get("drop_ids") or [])
                    if d in active and active[d]["status"] == "active"]
        if keep_id not in active or active[keep_id]["status"] != "active" or not drop_ids:
            continue
        keep = active[keep_id]
        # Umbrella guard (deterministic, required): never merge two categories
        # that share the same non-null `umbrella` value -- they are intentionally
        # distinct sub-codes of one umbrella (e.g. M1/M2/M3 under
        # schema-structure-discovery). Curtail any drop_id whose umbrella equals
        # the keep category's umbrella; if that empties the group, skip it.
        # Non-umbrella merges and emergent-buffer absorption are unaffected.
        keep_umb = keep.get("umbrella")
        if keep_umb:
            protected = [d for d in drop_ids
                         if active[d].get("umbrella") == keep_umb]
            if protected:
                print(f"  [umbrella-guard] {vocab}: refused to merge "
                      f"{protected} into {keep_id} (shared umbrella "
                      f"'{keep_umb}'); kept as distinct sub-codes",
                      file=sys.stderr, flush=True)
                drop_ids = [d for d in drop_ids if d not in protected]
            if not drop_ids:
                continue
        if mg.get("unified_name"):
            keep["name"] = mg["unified_name"]
        if mg.get("unified_definition"):
            keep["definition"] = mg["unified_definition"]
        for did in drop_ids:
            drop = active[did]
            for tid in drop["trace_ids"]:
                _add_trace(keep, tid)
            for al in drop["aliases"]:
                if al not in keep["aliases"]:
                    keep["aliases"].append(al)
            keep["exemplars"].extend(drop["exemplars"])
            keep["provenance"] = f"{keep['provenance']} | merged<-{did}:{drop['provenance']}"
            drop["status"] = f"merged_into:{keep_id}"
        done.append({"keep_id": keep_id, "drop_ids": drop_ids,
                     "unified_name": keep["name"]})
    return done


# --------------------------------------------------------------------------- #
# Outputs
# --------------------------------------------------------------------------- #
def write_candidate_json(codebook_dir: str, vocab: str, vstate: dict):
    active = vstate[vocab]["active"]
    out = []
    for rec in active.values():
        r = dict(rec)
        r["support"] = len(rec["trace_ids"])
        r["trace_ids"] = sorted(rec["trace_ids"])
        r["exemplars"] = rec["exemplars"][:MAX_EXEMPLARS]
        out.append(r)
    path = os.path.join(codebook_dir, f"{vocab}.candidate.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)


def write_proposed_md(codebook_dir: str, vstate: dict, args):
    L = []
    w = L.append
    w("# Proposed codebook (Stage 1 candidate)\n")
    w(f"_Generated {date.today().isoformat()} from `{args.indir}` "
      f"(set=`{args.set}`, batch-size={args.batch_size}, model=`{MODEL}`)._\n")
    w("Candidate (not frozen). Seeds are a warm start with no protection; they "
      "compete on equal footing and only `provenance` rides through merges.\n")
    for vocab in VOCABS:
        active = vstate[vocab]["active"]
        live = [r for r in active.values() if r["status"] == "active"]
        live.sort(key=lambda r: (-len(r["trace_ids"]), r["id"]))
        w(f"## {vocab.capitalize()} ({len(live)} active)\n")
        for rec in live:
            track = f" · track=`{rec['track']}`" if rec.get("track") else ""
            w(f"### {rec['id']} — {rec['name']}  (support {len(rec['trace_ids'])}){track}")
            w(f"- **Definition:** {rec['definition']}")
            w(f"- **Provenance:** {rec['provenance']}")
            exs = sorted(rec["exemplars"], key=lambda e: -len(e.get("quote") or ""))[:MAX_EXEMPLARS]
            if exs:
                w("- **Exemplars:**")
                for e in exs:
                    q = (e.get("quote") or "").replace("\n", " ")
                    w(f"    - `{e['trace_id']}` ({e.get('coder')}): {q}")
            if rec["aliases"]:
                w(f"- **Aliases ({len(rec['aliases'])}):** "
                  + "; ".join(rec["aliases"][:20]))
            w("")
        merged = [r for r in active.values() if r["status"] != "active"]
        if merged:
            w("#### Merged-away\n")
            for rec in merged:
                w(f"- `{rec['id']}` ({rec['name']}) -> {rec['status']}")
            w("")
    path = os.path.join(codebook_dir, "proposed_codebook.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")


def checkpoint(codebook_dir: str, state: dict):
    path = os.path.join(codebook_dir, "_induction_state.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def log_saturation(codebook_dir: str, entry: dict):
    path = os.path.join(codebook_dir, "saturation_log.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# --------------------------------------------------------------------------- #
# Dry-run preview
# --------------------------------------------------------------------------- #
def dry_run_preview(codebook_dir: str, sections: dict, vstate: dict,
                    batch: list[dict], args) -> str:
    L = []
    w = L.append
    w("# Batch-1 prompt preview (offline dry-run)\n")
    w(f"_Generated {datetime.now().isoformat(timespec='seconds')} — NO API call "
      f"was made._\n")
    w(f"Set=`{args.set}`, batch-size={args.batch_size}, model (live)=`{MODEL}`. "
      "Each placeholder is substituted with REAL batch-1 data. Both vocabularies "
      "(mechanisms, errors) share this one batch traversal; errors are only "
      "present on wrong/abstained traces.\n")
    w("## Batch-1 traces\n")
    for rec in batch:
        w(f"- `{rec['trace_id']}` — verdict `{rec['verdict']}`, "
          f"category {rec.get('category')}, project {rec.get('project')}")
    w("")
    for vocab in VOCABS:
        active = vstate[vocab]["active"]
        payload, _ = batch_codes_for_prompt(batch, vocab)
        active_json = json.dumps(active_for_prompt(active), ensure_ascii=False, indent=2)
        merge_active_json = json.dumps(active_for_merge_prompt(active),
                                       ensure_ascii=False, indent=2)
        buffer_json = json.dumps(buffer_for_prompt(vstate[vocab]["buffer"]),
                                 ensure_ascii=False, indent=2)
        batch_json = json.dumps(payload, ensure_ascii=False, indent=2)
        w(f"---\n\n# Vocabulary: {vocab.upper()}\n")
        w(f"## ASSIGNMENT prompt ({vocab})\n")
        w("````text")
        w(render_assignment(sections, vocab, len(batch), active_json,
                            buffer_json, batch_json))
        w("````\n")
        w(f"## MERGE prompt ({vocab})\n")
        w("````text")
        w(render_merge(sections, vocab, merge_active_json))
        w("````\n")
    path = os.path.join(codebook_dir, "_prompt_preview_batch1.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return path


# --------------------------------------------------------------------------- #
# Live run
# --------------------------------------------------------------------------- #
def live_run(codebook_dir: str, sections: dict, state: dict, records: list[dict], args):
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.getcwd(), ".env"))
    from src.harness.llm import init_llm

    # Pin the GLM client to IPv4 (the v6 route to api.z.ai is a blackhole on
    # this host); ChatOpenAI forwards these straight to the openai client.
    http_client, http_async_client = _ipv4_http_clients()
    llm = init_llm(MODEL, temperature=0, request_timeout=_REQUEST_TIMEOUT_S,
                   http_client=http_client, http_async_client=http_async_client)
    retryable = _retryable_excs()
    vstate = state["vocab"]
    batch_size = state["batch_size"]
    batches = [records[i:i + batch_size] for i in range(0, len(records), batch_size)]
    n_batches = len(batches)
    stop_batch = n_batches
    if args.max_batches is not None:
        stop_batch = min(n_batches, state["next_batch"] + args.max_batches)

    def call(prompt: str) -> dict:
        # Bounded retry on transient connection/TLS faults (see _RETRY_* above):
        # the IPv4 route to z.ai works but occasionally drops a TLS handshake
        # that succeeds on immediate retry. 429/quota gets a longer sleep so we
        # do not retry-storm a real rate limit.
        attempt = 0
        while True:
            try:
                resp = llm.invoke(prompt).content
                break
            except retryable as exc:
                if attempt >= _RETRY_MAX_ATTEMPTS - 1:
                    raise
                wait = min(_RETRY_BASE_S * (2 ** attempt), _RETRY_CEILING_S)
                print(f"  [retry] transient network error "
                      f"({type(exc).__name__}: {exc}); attempt "
                      f"{attempt + 1}/{_RETRY_MAX_ATTEMPTS}, sleeping {wait:.1f}s",
                      flush=True)
                time.sleep(wait)
                attempt += 1
            except Exception as exc:  # noqa: BLE001
                if _is_rate_limit(exc) and attempt < _RETRY_MAX_ATTEMPTS - 1:
                    print(f"  [backoff] rate limit ({type(exc).__name__}); "
                          f"sleeping {_RATE_LIMIT_SLEEP_S:.0f}s", flush=True)
                    time.sleep(_RATE_LIMIT_SLEEP_S)
                    attempt += 1
                    continue
                raise
        return robust_load(resp if isinstance(resp, str) else str(resp))

    async def acall(prompt: str) -> dict:
        # Async sibling of call(): same bounded retry envelope, used ONLY for the
        # concurrent ASSIGNMENT calls (--parallel). Consolidation/merge stay on
        # the sync call() path so promote/merge remain sequential + deterministic.
        attempt = 0
        while True:
            try:
                resp = (await llm.ainvoke(prompt)).content
                break
            except retryable as exc:
                if attempt >= _RETRY_MAX_ATTEMPTS - 1:
                    raise
                wait = min(_RETRY_BASE_S * (2 ** attempt), _RETRY_CEILING_S)
                print(f"  [retry] transient network error "
                      f"({type(exc).__name__}: {exc}); attempt "
                      f"{attempt + 1}/{_RETRY_MAX_ATTEMPTS}, sleeping {wait:.1f}s",
                      flush=True)
                await asyncio.sleep(wait)
                attempt += 1
            except Exception as exc:  # noqa: BLE001
                if _is_rate_limit(exc) and attempt < _RETRY_MAX_ATTEMPTS - 1:
                    print(f"  [backoff] rate limit ({type(exc).__name__}); "
                          f"sleeping {_RATE_LIMIT_SLEEP_S:.0f}s", flush=True)
                    await asyncio.sleep(_RATE_LIMIT_SLEEP_S)
                    attempt += 1
                    continue
                raise
        return robust_load(resp if isinstance(resp, str) else str(resp))

    def consolidate_and_checkpoint(bi: int):
        # Consolidation (every batch): promote then merge, per vocabulary --
        # STRICTLY sequential + deterministic. Identical to the original serial
        # path; checkpoint after each batch so --resume can continue cleanly.
        total_promoted = 0
        sat_entry = {"batch": bi, "ts": datetime.now().isoformat(timespec="seconds")}
        for vocab in VOCABS:
            promoted = promote(vstate, vocab, args.promote_min, bi)
            total_promoted += len(promoted)
            active = vstate[vocab]["active"]
            merge_prompt = render_merge(
                sections, vocab,
                json.dumps(active_for_merge_prompt(active), ensure_ascii=False, indent=2))
            merge_result = call(merge_prompt)
            merged = execute_merges(vstate, vocab, merge_result.get("merges", []))
            sat_entry[vocab] = {
                "promoted": promoted,
                "merged": merged,
                "active_count": sum(1 for r in active.values() if r["status"] == "active"),
                "buffer_count": len(vstate[vocab]["buffer"]),
            }

        if total_promoted == 0:
            state["saturation_streak"] += 1
        else:
            state["saturation_streak"] = 0
        if state["saturation_streak"] >= SATURATION_STOP:
            state["saturated"] = True
        sat_entry["promotions_this_batch"] = total_promoted
        sat_entry["saturation_streak"] = state["saturation_streak"]
        log_saturation(codebook_dir, sat_entry)

        state["next_batch"] = bi + 1
        checkpoint(codebook_dir, state)
        for vocab in VOCABS:
            write_candidate_json(codebook_dir, vocab, vstate)
        write_proposed_md(codebook_dir, vstate, args)
        print(f"[batch {bi + 1}/{n_batches}] promoted={total_promoted} "
              f"streak={state['saturation_streak']}", flush=True)

    group_size = max(1, args.parallel)
    # --no-early-stop: a state that already saturated (e.g. resuming the run that
    # stopped at batch 7) must NOT instantly stop. Clear the persisted flag so
    # the loop continues from next_batch; saturation is still recomputed+logged.
    if args.no_early_stop and state.get("saturated"):
        print("--no-early-stop: clearing prior saturated flag; continuing.",
              flush=True)
        state["saturated"] = False

    async def run_loop():
        bi = state["next_batch"]
        while bi < stop_batch:
            # Saturation break is gated behind --no-early-stop (Change B). When
            # --no-early-stop is set we never break; every batch is processed.
            if not args.no_early_stop and state.get("saturated"):
                print(f"saturation reached before batch {bi}; stopping.", flush=True)
                break
            group = list(range(bi, min(bi + group_size, stop_batch)))
            # Active+buffer snapshot taken ONCE at group start; every assignment
            # call in the group sees the SAME vocabulary. Promotions propagate at
            # group boundaries; the buffer-dedup in apply_assignments folds a
            # novel concept that appears in multiple same-group batches.
            snapshot = {}
            for vocab in VOCABS:
                active = vstate[vocab]["active"]
                snapshot[vocab] = (
                    json.dumps(active_for_prompt(active), ensure_ascii=False, indent=2),
                    json.dumps(buffer_for_prompt(vstate[vocab]["buffer"]),
                               ensure_ascii=False, indent=2),
                )
            jobs = []   # (batch_idx, vocab, lookup) aligned positionally with coros
            coros = []
            for gbi in group:
                batch = batches[gbi]
                for vocab in VOCABS:
                    payload, lookup = batch_codes_for_prompt(batch, vocab)
                    if not any(p[vocab] for p in payload):
                        continue  # no labels of this vocab in the batch
                    active_json, buffer_json = snapshot[vocab]
                    batch_json = json.dumps(payload, ensure_ascii=False, indent=2)
                    prompt = render_assignment(sections, vocab, len(batch),
                                               active_json, buffer_json, batch_json)
                    jobs.append((gbi, vocab, lookup))
                    coros.append(acall(prompt))
            # Fire the group's ASSIGNMENT calls. With --parallel 1 we await them
            # ONE AT A TIME (max 1 in-flight) so the call footprint matches the
            # original sequential path exactly -- no regression, and no extra
            # concurrency pressure on the provider. With --parallel >= 2 the
            # whole group's calls run concurrently via asyncio.gather. On hard
            # failure the last per-batch checkpoint (<= group start) stays intact,
            # so --resume re-runs only this group rather than losing progress.
            try:
                if group_size == 1:
                    results = [await c for c in coros]
                else:
                    results = await asyncio.gather(*coros)
            except Exception as exc:  # noqa: BLE001
                print(f"  [group-fail] assignment calls for batches "
                      f"{[g + 1 for g in group]} failed ({type(exc).__name__}: "
                      f"{exc}); checkpoint at batch {state['next_batch']} intact, "
                      f"resume to retry.", flush=True)
                checkpoint(codebook_dir, state)
                raise
            assign_by = {}
            for (gbi, vocab, lookup), result in zip(jobs, results):
                assign_by[(gbi, vocab)] = (result, lookup)
            # Apply assignments + consolidate STRICTLY SEQUENTIALLY in batch
            # order; checkpoint after each batch -- exactly as the serial path.
            for gbi in group:
                for vocab in VOCABS:
                    entry = assign_by.get((gbi, vocab))
                    if entry is None:
                        continue
                    result, lookup = entry
                    apply_assignments(vstate, vocab,
                                      result.get("assignments", []), lookup, gbi)
                consolidate_and_checkpoint(gbi)
            bi = group[-1] + 1

    asyncio.run(run_loop())
    print("INDUCTION COMPLETE", flush=True)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--indir", default=DEFAULT_INDIR,
                    help="Stage-0 output dir (holds the records + codebook/ subdir)")
    ap.add_argument("--records", default=None,
                    help="records JSON (default: <indir>/_consolidation_records.json)")
    ap.add_argument("--prompt", default=DEFAULT_PROMPT,
                    help="induction prompt template")
    ap.add_argument("--set", default="orig", choices=["orig", "rerun_divergent", "all"],
                    help="trace set to induce over (default orig; the 514). "
                         "rerun_divergent is reserved for the flip sub-study.")
    ap.add_argument("--batch-size", type=int, default=5,
                    help="traces per batch (default 5, max recommended 10)")
    ap.add_argument("--promote-min", type=int, default=3,
                    help="distinct-trace recurrence to promote a buffer candidate")
    ap.add_argument("--max-batches", type=int, default=None,
                    help="cap this run to N batches from the resume point "
                         "(default: no limit; processes all batches)")
    ap.add_argument("--no-early-stop", action="store_true",
                    help="compute and LOG saturation each batch but NEVER stop "
                         "early; process every batch (or up to --max-batches)")
    ap.add_argument("--parallel", type=int, default=1,
                    help="number of batches whose ASSIGNMENT calls run "
                         "concurrently per group (default 1 = sequential). "
                         "Consolidation/merge always stay sequential + "
                         "deterministic; --parallel 1 == current behavior.")
    ap.add_argument("--dry-run", action="store_true",
                    help="render the batch-1 prompts offline (NO API call) and exit")
    ap.add_argument("--resume", action="store_true",
                    help="resume from <indir>/codebook/_induction_state.json")
    ap.add_argument("--fresh", action="store_true",
                    help="explicitly start over, overwriting any existing "
                         "checkpoint. Required to reinitialize when a state file "
                         "exists (guards against clobbering an in-progress run).")
    args = ap.parse_args(argv)

    if args.resume and args.fresh:
        print("error: pass only one of --resume / --fresh", file=sys.stderr)
        return 2

    indir = args.indir
    codebook_dir = os.path.join(indir, CODEBOOK_SUBDIR)
    records_path = args.records or os.path.join(indir, DEFAULT_RECORDS)

    if not os.path.isdir(codebook_dir):
        print(f"error: codebook dir not found: {codebook_dir}", file=sys.stderr)
        return 2
    if not os.path.isfile(records_path):
        print(f"error: records not found: {records_path}", file=sys.stderr)
        return 2

    sections = load_template(args.prompt)
    records = load_records(records_path, args.set)
    if not records:
        print(f"error: no records for set={args.set}", file=sys.stderr)
        return 2

    # Seeds -> active warm start. Build / load driver state.
    state_path = os.path.join(codebook_dir, "_induction_state.json")
    # Resume safety: if a checkpoint exists, require an explicit decision so we
    # never silently clobber an in-progress run. --dry-run is exempt (it makes no
    # API call and never writes the state file). Manually deleting the state file
    # still counts as fresh.
    if (os.path.isfile(state_path) and not args.resume and not args.fresh
            and not args.dry_run):
        print(f"error: checkpoint exists at {state_path}; pass --resume to "
              f"continue or --fresh to start over", file=sys.stderr)
        return 2
    if args.resume and os.path.isfile(state_path) and not args.dry_run:
        state = json.load(open(state_path, encoding="utf-8"))
        print(f"resumed state from batch {state['next_batch']}", flush=True)
    else:
        state = {
            "set": args.set,
            "batch_size": args.batch_size,
            "promote_min": args.promote_min,
            "next_batch": 0,
            "saturation_streak": 0,
            "saturated": False,
            "vocab": load_seeds(codebook_dir),
        }

    vstate = state["vocab"]
    n_batches = (len(records) + args.batch_size - 1) // args.batch_size
    seed_counts = {v: sum(1 for r in vstate[v]["active"].values()) for v in VOCABS}
    print(f"set={args.set}: {len(records)} traces / {n_batches} batches "
          f"(batch-size {args.batch_size})", flush=True)
    print(f"seeds loaded: mechanisms={seed_counts['mechanisms']}, "
          f"errors={seed_counts['errors']}", flush=True)

    if args.dry_run:
        batch = records[:args.batch_size]
        path = dry_run_preview(codebook_dir, sections, vstate, batch, args)
        size = os.path.getsize(path)
        print(f"DRY-RUN: wrote batch-1 preview -> {path} ({size} bytes)", flush=True)
        print("DRY-RUN: zero API calls made.", flush=True)
        return 0

    live_run(codebook_dir, sections, state, records, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
