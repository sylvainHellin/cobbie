# Closed-coding census instruction: agent trace classification

## Context
You are analyzing a single trace from an AI agent that answers natural-language questions about a Building Information Model (BIM, an IFC file) by writing and running Python code in a feedback loop (a CodeAct agent). The trace below contains, in order: a short metadata header, the agent's system prompt, the question it was asked, every code step it executed with the resulting observation, its final answer, the ground-truth answer, and an independent judge's verdict and reasoning.

This is **closed coding** for a research study. Unlike open coding, you do **not** invent labels. You assign each trace to a **fixed, frozen vocabulary** of mechanism and error categories, given below. Two hard rules:

1. **Assign only the listed ids.** Judge by the underlying agent behavior, not surface wording. Map behavior to the closest listed category; do not split hairs. The only escape hatch is `M-Other` / `E-Other`, which require a named free-text pattern (see the Other rule for each vocabulary).
2. **Do not re-judge.** Copy the `verdict` verbatim from the trace header (`correct`, `wrong`, or `abstained`). You never overturn the judge.

Multi-label is allowed and expected: a trace typically carries several mechanisms, and a failed trace can carry several errors.

## Mechanism vocabulary (RQ2) — coded on EVERY trace
{{MECH_SCOPE_NOTE}}

**Other rule (M-Other):** {{MECH_OTHER_RULE}}

Categories (assign by id):
{{MECH_CATEGORIES}}

## Error vocabulary (RQ3) — coded ONLY on `wrong` and `abstained` traces
{{ERR_SCOPE_NOTE}}

If the header verdict is `correct`, the error list MUST be empty (`"error_ids": []`). Code errors only when the verdict is `wrong` or `abstained`.

The error vocabulary has two tracks. `track=agent` ids are agent-caused failures. `track=non-agent` ids (E7 reference/judge artifact, E14 environment/infrastructure failure) are exogenous — they still get coded when they apply, but they attribute the failure to the reference/judge or the execution environment rather than the agent.

**Other rule (E-Other):** {{ERR_OTHER_RULE}}

Categories (assign by id):
{{ERR_CATEGORIES}}

{{TRACE}}

## Instruction
Analyze the full trace above and return a single JSON object with exactly these keys:

- `"trace_id"`: the trace id (format `q<question_id>_r<repeat_idx>_<verdict>`; reconstruct from the header ids and verdict, or copy it if shown).
- `"verdict"`: the judge verdict from the header (`correct`, `wrong`, or `abstained`). Copy it; do not re-judge.
- `"mechanism_ids"`: a list of the mechanism ids that apply (from `M1`–`M10`, or `M-Other`). Assign on every trace. Use only listed ids.
- `"error_ids"`: a list of the error ids that apply (from `E1`, `E2`, `E4a`, `E4b`, `E4c`, `E-Other`, `E7`, `E14`). MUST be `[]` when the verdict is `correct`. Only populate on `wrong`/`abstained` traces. Use only listed ids.
- `"mechanism_other_note"`: `null` unless `mechanism_ids` contains `M-Other`, in which case a non-empty free-text string naming the specific uncatalogued pattern (required).
- `"error_other_note"`: `null` unless `error_ids` contains `E-Other`, in which case a non-empty free-text string naming the specific uncatalogued pattern (required).
- `"evidence"`: an object mapping each assigned id (mechanism or error) to a short free-text justification — a step number and/or a brief quote grounding the code (e.g. `"M8": "Step 4: converted per-slab volumes to m3 (x0.0283168)"`).

Return only the JSON object, with no surrounding prose.
