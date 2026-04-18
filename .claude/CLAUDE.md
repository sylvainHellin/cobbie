# CLAUDE.md

Reproduction package for the EC³ 2026 paper *Assessing the Viability of LLM
Agents for Generating Reusable Compliance Checking Functions*
(Fuchs, Hellin, Borrmann). Keep the repo narrowly scoped to the ACC
pipeline described below.

## Build, Lint & Type Check

```bash
uv run ruff check .
uvx ty check src
```

All Python commands must use `uv run`.

## MLflow Server

Start before any training / extraction script:

```bash
cd .mlflow
uv run mlflow server --host 127.0.0.1 --port 5000 \
  --backend-store-uri sqlite:///mlflow.sqlite \
  --uvicorn-opts "--timeout-keep-alive 120 --workers 1"
```

`--workers 1` is required to avoid SQLite contention on concurrent writes.

## API Keys

Required in `.env` (see `.env.example`):

- `CONTEXT7_API_KEY` — `query_ifcopenshell_docs` fetches from Context7's
  `/ifcopenshell/ifcopenshell` library.
- `Z_AI_API_KEY` — default BAML client (`GLM_4_7`) used to produce the
  paper results.

Optional: `OPENROUTER_API_KEY` — swap `client GLM_4_7` → `client GLM_4_7_OpenRouter`
in any `.baml` function to run `z-ai/glm-4.7` via OpenRouter instead.

## ACC Pipeline

The 4/4/4 model split is frozen in `acc/config/model_splits.json` (paper
Table 1). The greedy splitter that produced it is `scripts/run_acc_split_models.py`;
ground-truth fixes since the paper have changed the input stats, so
re-running it now yields a *different* split. Treat the committed JSON as
authoritative; do not regenerate when reproducing.

| Step | Script | Output |
|---|---|---|
| 1. Run Solibri | `scripts/run_acc_check.py` | `acc/res/<model>/issues/topics.json` |
| 2. Ground truth | `scripts/generate_ground_truth.py` | `acc/res/<model>/ground_truth.json` |
| 3. Train tools | `scripts/run_acc_training_batched.sh` | MLflow runs + `acc/tools/*.py` |
| 4. Evaluate | `scripts/run_acc_tool_evaluation.py` | `outputs/acc/tool_evaluation_*.{json,md}` |
| 5. Paper outputs | `scripts/extract_acc_metadata.py`, `extract_acc_traces.py`, `generate_acc_results_table.py` | `outputs/ec3/*` |

Training defaults match the paper: `--max-iterations 15` (n_max_iter),
`--max-retries 2` (retry budget). Training is batched as separate
subprocesses to prevent `ifcopenshell` C++ object accumulation; the shell
wrapper handles run-id wiring and resume via `--continue <mlflow_run_id>`.

## Architecture

- **`src/agents/create_acc_function.py`** — Code-Act-style BAML loop that
  develops a candidate ACC check function. Writes, executes, and iterates
  until the function compiles and passes in-loop sanity tests.
- **`src/agents/assess_acc_tool.py`** — Diagnoses why a tool under-performed
  on validation and decides `keep_tool` vs `retry_with_hint`.
- **`src/acc/guid_comparison.py`** — P/R/F1 against `ground_truth.json`.
- **`src/util/code_act_inner_loop.py`** — `_execute_code_action` sandbox
  runner shared by the tool-creation loop.
- **`src/tools/initial/`** — Pre-loaded utilities the trained tools may call:
  `classify_spaces` (mirrors Solibri's semantic space-usage classifications
  so the agent is on equal footing with the verifier, per §Experimental
  Setup of the paper) + `query_ifcopenshell_docs`.

## BAML

Sources in `src/baml/baml_src/`, generated client in `src/baml/baml_client/`.
Regenerate after any `.baml` change:

```bash
cd src/baml && uv run baml-cli generate
```

Active BAML functions: `HelperFunctionCreator`, `ACCToolAssessor`.

## Generated Outputs

All generated files go under `outputs/` — either `outputs/acc/`
(tool-eval reports) or `outputs/ec3/` (paper artefacts). Do not write
generated files elsewhere. Run-time logs go to `logs/` at repo root.

## Development Rules

- Use `uv run` for all Python commands.
- Update `CLAUDE.md` / `README.md` when the pipeline, dependencies, or
  required env vars change.
- Before claiming a change is done: `uv run ruff check .` and
  `uvx ty check <changed paths>` must pass cleanly *on the changed code*
  (pre-existing warnings in the repo exist — do not regress them).
- Use `context7` MCP for library docs (`/mlflow/mlflow`,
  `/websites/boundaryml`) before writing non-trivial API calls.
