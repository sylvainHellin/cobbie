# CLAUDE.md

This branch (`acc_published`) is the slim reproduction package for the EC3
paper on ACC (Automated Code Compliance) checking with Cobbie. Only ACC-related
modules are kept; the BIM-QA training/evaluation stack on `main` has been
removed here.

## Build, Lint & Type Check

```bash
uv run ruff check .
uvx ty check src
```

All Python commands must use `uv run`.

## MLflow Server

Start before any training/extraction script:

```bash
cd .mlflow
uv run mlflow server --host 127.0.0.1 --port 5000 \
  --backend-store-uri sqlite:///mlflow.sqlite \
  --uvicorn-opts "--timeout=120 -w 1"
```

`-w 1` is required to avoid SQLite contention on concurrent writes.

## ACC Pipeline

| Step | Script | Output |
|---|---|---|
| 1. Split models | `scripts/run_acc_split_models.py` | `acc/config/model_splits.json` |
| 2. Run Solibri | `scripts/run_acc_check.py` | `acc/res/<model>/issues/topics.json` |
| 3. Ground truth | `scripts/generate_ground_truth.py` | `acc/res/<model>/ground_truth.json` |
| 4. Train tools | `scripts/run_acc_training_batched.sh` | MLflow runs + `acc/tools/*.py` |
| 5. Evaluate | `scripts/run_acc_tool_evaluation.py` | `outputs/acc/tool_evaluation_*.{json,md}` |
| 6. Paper outputs | `scripts/extract_acc_metadata.py`, `extract_acc_traces.py`, `generate_acc_results_table.py` | `outputs/ec3/*` |

Training is batched as separate subprocesses to prevent `ifcopenshell`
C++ object accumulation. The shell script handles run-id wiring and resume
via `--continue <mlflow_run_id>`.

## Architecture

- **`src/agents/create_acc_function.py`** — CodeAct-style BAML loop that
  develops a candidate ACC check function. Writes, executes, and iterates
  until the function compiles and passes in-loop sanity tests.
- **`src/agents/assess_acc_tool.py`** — Diagnoses why a tool under-performed
  on validation and decides `keep_tool` vs `retry_with_hint`.
- **`src/acc/guid_comparison.py`** — P/R/F1 against `ground_truth.json`.
- **`src/util/code_act_inner_loop.py`** — `_execute_code_action` sandbox
  runner shared by the tool-creation loop.
- **`src/tools/initial/`** — Pre-loaded utilities the trained tools may call:
  `classify_spaces`, `query_ifcopenshell_docs` (fetches from Context7's
  `/ifcopenshell/ifcopenshell` library; requires `CONTEXT7_API_KEY`).

## BAML

Sources in `src/baml/baml_src/`, generated client in `src/baml/baml_client/`.
Regenerate after any `.baml` change:

```bash
uv run baml-cli generate
```

Active BAML functions: `HelperFunctionCreator`, `ACCToolAssessor`.

## Generated Outputs

All generated files go under `outputs/` — either `outputs/acc/` (tool-eval
reports) or `outputs/ec3/` (paper artefacts). Do not write generated files
elsewhere.

## Development Rules

- Use `uv run` for all Python commands.
- No need to update CLAUDE.md / README.md unless the pipeline itself changes.
- Before claiming a change is done: `uv run ruff check .` and
  `uvx ty check <changed paths>` must pass cleanly *on the changed code*.
  (There are pre-existing warnings in the repo; do not regress them.)
- Use `context7` MCP for library docs (`/mlflow/mlflow`, `/websites/boundaryml`)
  before writing non-trivial API calls.

## Non-goals on this branch

The BIM-QA pipeline, IFC-Bench dataset, human-judge IRR computation, baseline
system, manual tools, and the dynamically-created BIM-QA tools have all been
removed. Do not reintroduce them here — they live on `main`.
