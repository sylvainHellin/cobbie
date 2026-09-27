# Codebook induction instruction: constant-comparative axial coding

## Context
You are inducing a small, controlled vocabulary from free-text open codes produced by two independent coders over agent traces. Each trace is one run of an AI agent that answers a natural-language question about a Building Information Model (BIM/IFC file) by writing and running Python in a feedback loop (a CodeAct agent). You are NOT re-reading the traces; you are clustering the open codes themselves.

There are two parallel vocabularies, each induced the same way but kept separate:
- **mechanisms** — moves the agent used to locate, compute, or estimate the answer (present on every trace).
- **errors** — what went wrong (present only on wrong/abstained traces).

This prompt template carries two distinct calls, ASSIGNMENT and MERGE. The driver runs ASSIGNMENT once per batch (per vocabulary) and MERGE once per consolidation (per vocabulary). You are stateless: the driver owns all vocabulary state and supplies it to you each call. The placeholders below (`{{...}}`) are substituted by the driver. Judge by the underlying agent behavior, not by surface wording; keep the vocabulary small (working ceiling ~10 categories per vocabulary).

The vocabulary has two tiers:
- **active** — the controlled categories. You may map a label onto one of these (preferred) but you may NOT mint new active categories; only the driver promotes.
- **buffer** — candidate phrasings awaiting recurrence. You may map a label onto an existing buffer candidate or propose a NEW buffer candidate.

---

## CALL A — ASSIGNMENT

You are assigning the open-code labels from a batch of {{N_TRACES}} traces to the `{{VOCAB}}` vocabulary.

### Active vocabulary (existing categories — prefer these; you may NOT create new ones)
```json
{{ACTIVE_VOCAB_JSON}}
```
Each active entry is `{"id","name","definition","sample_aliases":[...]}`.

### Buffer candidates (phrasings awaiting recurrence)
```json
{{BUFFER_JSON}}
```
Each buffer entry is `{"id","phrasing","occurrences"}`.

### Batch open codes
```json
{{BATCH_CODES_JSON}}
```
Each batch entry is `{"trace_id","verdict","{{VOCAB}}":[{"label","evidence"}, ...]}`. Both coders' labels are pooled into the one list per trace.

### Instruction
For EACH `{{VOCAB}}` label in the batch, choose exactly one assignment by its underlying behavior (not its wording):
- `"kind": "active"` — the label expresses an existing active category. Set `"decision": "active"` and `"target_id"` to that category id. **Prefer this whenever the behavior already fits an active category.**
- `"kind": "buffer"` — the label matches an existing buffer candidate. Set `"decision": "buffer"` and `"target_id"` to that buffer id.
- `"kind": "new"` — the label is a genuinely new behavior not covered by any active category or buffer candidate. Set `"decision": "new"` and propose `"new_name"` (short descriptive name) and `"new_definition"` (one sentence). It will stage in the buffer; you may NOT mint active categories.

Rules:
- You may NOT create active categories — novelties go to the buffer via `"new"`.
- Map to an active category whenever the behavior fits; only buffer/new when it is genuinely distinct.
- Keep the vocabulary small: do not split hairs over wording; fold rephrasings of the same behavior together.
- Give a one-line `"rationale"` per assignment.

Return ONLY this JSON object, no surrounding prose:
```json
{
  "assignments": [
    {
      "trace_id": "<trace id>",
      "label": "<the open-code label verbatim>",
      "kind": "active | buffer | new",
      "decision": "active | buffer | new",
      "target_id": "<active or buffer id; omit for new>",
      "new_name": "<only when kind=new>",
      "new_definition": "<one sentence; only when kind=new>",
      "rationale": "<one line>"
    }
  ]
}
```

---

## CALL B — MERGE

You are consolidating the `{{VOCAB}}` active vocabulary to hold it small.

### Active vocabulary
```json
{{ACTIVE_VOCAB_JSON}}
```
Each active entry is `{"id","name","definition","sample_aliases":[...]}`; some entries also carry an `"umbrella"` field.

### Instruction
Propose merges of active categories that denote the same underlying agent behavior (mechanisms) or the same failure mode (errors). Aim to keep the active set at a working ceiling of ~10 categories. NEVER merge categories that denote distinct behaviors just to hit the ceiling — a forced loss of a real distinction is worse than a slightly larger set. Never merge two categories that share the same `umbrella` value — they are intentionally distinct sub-codes of one umbrella; keep them separate. If nothing should be merged, return an empty list.

For each merge group choose one `keep_id` (the category to retain) and one or more `drop_ids` (absorbed into it). The driver executes the merge deterministically (set-union of supporting traces, aliases, exemplars; provenance concatenated); you only propose the semantic grouping and the unified name/definition.

Return ONLY this JSON object, no surrounding prose:
```json
{
  "merges": [
    {
      "keep_id": "<id to retain>",
      "drop_ids": ["<id absorbed>", "..."],
      "unified_name": "<name for the merged category>",
      "unified_definition": "<one sentence>",
      "rationale": "<why these denote the same behavior>"
    }
  ]
}
```
