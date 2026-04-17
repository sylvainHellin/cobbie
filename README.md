# ACC Function Generation — EC³ 2026 Reproduction Package

Reproduction package for:

> Fuchs, S., Hellin, S., Borrmann, A. **Assessing the Viability of LLM
> Agents for Generating Reusable Compliance Checking Functions.**
> *2026 European Conference on Computing in Construction (EC³)*,
> Corfu, Greece, July 12–15, 2026.

An LLM agent (using the Code-Act pattern) iteratively generates Python
helper functions that implement building-code compliance checks against IFC
models. Solibri's rule engine provides the ground truth; the generated
functions are trained, validated, and tested against its per-element
verdicts.

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
          ▼   (Code-Act create + validation + assessment loop)
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
  - `Z_AI_API_KEY` — required; the default BAML client (`GLM_4_7`) calls
    z.ai directly. This is the configuration the paper was produced with.
  - `OPENROUTER_API_KEY` — optional backup. Swap the `client GLM_4_7` line in
    any `.baml` function to `client GLM_4_7_OpenRouter` to run the same model
    (`z-ai/glm-4.7`) via OpenRouter if your z.ai key is unavailable.
- Solibri Anywhere (only needed to regenerate `topics.json` from `.ifc` files;
  the committed `topics.json` already covers all 12 models)

### BIM models

The 12 `.ifc` models used in the paper live under `acc/bim_models/<name>/`.
Per Table 1 of the paper, they are split:

|              | Training      | Validation  | Test          |
|--------------|---------------|-------------|---------------|
|              | 141*          | 103*        | 4351          |
|              | AC20          | 166*        | Digital Hub   |
|              | Dental Clinic | FZK House   | S. MacAlister |
|              | Duplex        | Smiley West | WBDG Office   |

Models marked `*` are from the authors' BIM fundamentals course; the
remaining nine are from **IFCBench** (Hellin et al., 2025).

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
  --uvicorn-opts "--timeout-keep-alive 120 --workers 1"
```

`--workers 1` avoids SQLite write contention during concurrent run logging.

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
bash scripts/run_acc_training_batched.sh --nb-samples 16 --batch-size 1
```

Defaults match the paper: `--max-iterations 15` (n_max_iter) and
`--max-retries 2` (retry budget for validation-driven refinement).

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
└── tools/                # Generated check_*.py (the paper's tools)

src/
├── acc/                  # Solibri integration, BCF parsing, GUID comparison
├── agents/               # create_acc_function.py, assess_acc_tool.py
├── baml/                 # BAML sources + generated client
├── config.py             # Paths & env-var loading
├── tools/initial/        # classify_spaces (mirrors Solibri's semantic
│                         #   space-usage classifications so the agent is on
│                         #   equal footing with the verifier, per §Experi-
│                         #   mental Setup of the paper) + query_ifcopenshell_docs
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

```bibtex
@inproceedings{fuchs2026acc,
  title     = {Assessing the Viability of LLM Agents for Generating
               Reusable Compliance Checking Functions},
  author    = {Fuchs, Stefan and Hellin, Sylvain and Borrmann, Andr{\'e}},
  booktitle = {2026 European Conference on Computing in Construction (EC$^3$)},
  address   = {Corfu, Greece},
  year      = {2026},
  month     = jul,
}
```

## License

MIT — see [`LICENSE`](LICENSE).
