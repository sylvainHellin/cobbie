# Cobbie — ACC / EC3 Paper Reproduction

This branch contains the code and data required to reproduce the EC3 paper on
**Automated Code Compliance (ACC) checking** with Cobbie. It is a slim subset
of the full Cobbie repo — only the modules needed for the ACC pipeline remain.

Cobbie generates Python helper functions that implement building-code
compliance checks against IFC models. Solibri's rule engine provides the
ground truth; Cobbie's tools are trained to match its per-element verdicts.

## Pipeline Overview

```
  acc/bim_models/*.ifc
          │
          ▼   (Solibri rule engine)
   acc/res/<model>/issues/topics.json      ← run_acc_check.py
          │
          ▼
   acc/res/<model>/ground_truth.json       ← generate_ground_truth.py
          │
          ▼   (Cobbie CodeAct + validation + assessment loop)
   acc/tools/check_*.py                    ← run_acc_training.py
          │
          ▼   (execute tools on the test split)
   outputs/acc/tool_evaluation_*.{json,md} ← run_acc_tool_evaluation.py
          │
          ▼   (paper tables & traces)
   outputs/ec3/acc_{results,execution}_table.{csv,tex}
   outputs/ec3/acc_metadata.json
   outputs/ec3/acc_traces.json
```

## Prerequisites

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) package manager
- API keys in `.env` (see `.env.example`):
  - `CONTEXT7_API_KEY` — required; `query_ifcopenshell_docs` fetches IFC docs
    from [Context7](https://context7.com) (`/ifcopenshell/ifcopenshell`)
  - LLM provider key(s) for the training model (e.g. `OPENROUTER_API_KEY`,
    `ANTHROPIC_API_KEY`)
- Solibri Anywhere (only needed to regenerate `topics.json` from `.ifc` files;
  committed `topics.json` already covers all 12 models)

```bash
uv sync
cp .env.example .env     # fill in API keys and ROOT_PATH
```

## MLflow

Training and evaluation log to MLflow. Start the tracking server before
running any training / extraction script:

```bash
cd .mlflow
uv run mlflow server \
  --host 127.0.0.1 --port 5000 \
  --backend-store-uri sqlite:///mlflow.sqlite \
  --uvicorn-opts "--timeout=120 -w 1"
```

The `-w 1` flag avoids SQLite write contention during concurrent run logging.

## Reproducing the Paper

All intermediate artefacts (`topics.json`, `ground_truth.json`,
`model_splits.json`, BAML client) are committed, so you can start at any step.

### 1. (Optional) Regenerate model split
```bash
uv run scripts/run_acc_split_models.py
```

### 2. (Optional) Re-run Solibri and extract BCF
```bash
uv run scripts/run_acc_check.py --all
```

### 3. Ground truth
```bash
uv run scripts/generate_ground_truth.py
```

### 4. Train tools (batched to avoid `ifcopenshell` memory growth)
```bash
bash scripts/run_acc_training_batched.sh --nb-samples 17 --batch-size 1
```

Follow the prompt for the MLflow run ID after the first batch, then reuse it
with `--continue <run_id>` for subsequent resumes.

### 5. Evaluate tools on the held-out test split
```bash
uv run scripts/run_acc_tool_evaluation.py
```

### 6. Generate paper outputs
```bash
uv run scripts/extract_acc_metadata.py      # outputs/ec3/acc_metadata.json
uv run scripts/extract_acc_traces.py        # outputs/ec3/acc_traces.json
uv run scripts/generate_acc_results_table.py  # outputs/ec3/acc_{results,execution}_table.{csv,tex}
```

## Repository Layout

```
acc/                      # ACC data & tools
├── bim_models/           # 12 IFC models (train / validate / test splits)
├── config/               # rule_templates.json, model_splits.json, coverage_matrix.csv
├── res/<model>/          # Solibri outputs + ground_truth.json per model
├── setup/                # Solibri rule sets, autorun config
└── tools/                # Cobbie-trained check_*.py (paper's tools)

src/
├── acc/                  # Solibri integration, BCF parsing, GUID comparison
├── agents/               # create_acc_function.py, assess_acc_tool.py
├── baml/                 # BAML sources + generated client
├── config.py             # Paths & env-var loading
├── tools/initial/        # classify_spaces, query_ifcopenshell_docs
└── util/                 # setup_logger, save_new_tool, code_act loop,
                          # python_executor, mlflow_utils

scripts/                  # Pipeline entry points (see above)
outputs/acc/              # Tool-evaluation reports
outputs/ec3/              # Paper tables, metadata, traces
```

## Development

```bash
uv run ruff check .
uvx ty check src
```

## Citation

If you use this code, please cite the EC3 paper. *(Citation details once
published.)*

## License

MIT
