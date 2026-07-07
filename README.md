# Cobbie: Code-Based BIM Information Extraction

An LLM-based multi-agent system for answering questions about BIM models in IFC format. Cobbie uses a dynamic tool creation architecture where the system learns to generate reusable Python functions during training, then applies them during inference.

> **Paper**: *BIM Information Extraction Through LLM-based Adaptive Exploration*, submitted to *Automation in Construction*. Authors: S. Hellin, S. Jang, S. Fuchs, S. Nousias, A. Borrmann.
> This repository accompanies the paper. Please cite it if you use this code or the IFC-Bench dataset.

## Features

- **Multi-agent architecture**: Specialized agents for code generation, verification, tool creation, debugging, and assessment
- **Dynamic tool creation**: Automatically generates and manages reusable Python functions during training
- **Multiple system configurations**: Agentic (Cobbie), static one-shot, and doc-augmented baselines
- **Comprehensive evaluation**: MLflow-tracked experiments with LLM-based answer grading
- **IFC-Bench dataset**: 200 questions across 10 IFC building models spanning 8 categories

## Quick Start

### Prerequisites

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) package manager
- API keys for at least one supported LLM provider (see `.env.example`)

### Installation

```bash
git clone <repository-url>
cd cobbie
uv sync
cp .env.example .env  # Then fill in your API keys
```

### Dataset Setup

The IFC-Bench dataset and IFC model files are hosted on HuggingFace:

1. **Download the dataset** from [ifc-bench-v2](https://huggingface.co/datasets/sylvainHellin/ifc-bench) on HuggingFace.
2. **Place the database** at `src/db/db.db`.
3. **Download the IFC model files** and place them under `src/db/bim_models/`. The database contains file paths referencing this directory -- update the `model_path` column in the `ifcmodels` table if your paths differ.

### MLflow Setup

MLflow is required for experiment tracking. Start it from the `.mlflow/` directory:

```bash
cd .mlflow
uv run mlflow server --host 127.0.0.1 --port 5000 \
  --backend-store-uri sqlite:///mlflow.sqlite \
  --uvicorn-opts "--timeout=120 -w 1"
```

Access the UI at http://127.0.0.1:5000. Use a single worker (`-w 1`) to avoid SQLite locking issues.

## Project Structure

```
cobbie/
├── src/
│   ├── agents/           # Multi-agent implementations
│   ├── analysis/         # Evaluation data extraction and analysis
│   ├── baml/
│   │   ├── baml_src/     # BAML agent definitions (source of truth)
│   │   └── baml_client/  # Auto-generated client (gitignored)
│   ├── baseline/         # Static baseline implementations
│   ├── db/               # Database layer, models, and queries
│   │   └── bim_models/   # IFC model files (gitignored, download from HF)
│   ├── docs_indexer/     # IfcOpenShell documentation retrieval (RAG)
│   ├── schemas/          # Pydantic data models
│   ├── tools/
│   │   ├── initial/      # Base tools (docs query, web search)
│   │   ├── created/      # Dynamically generated tools from training
│   │   └── manual/       # Manually curated tools
│   └── util/             # Utilities (metrics, execution, logging)
├── scripts/              # Training, evaluation, and analysis scripts
├── docs/                 # Architecture and dataset documentation
├── outputs/              # Generated reports and figures (gitignored)
└── .mlflow/              # MLflow tracking data (gitignored)
```

## Reproducing the Experiments

### Environment Variables

Copy `.env.example` to `.env` and fill in the required API keys. The minimum required key depends on which experiments you run:

| Provider | Key | Used by |
|---|---|---|
| Z.AI | `Z_AI_API_KEY` | GLM-4.7 (default model for all experiments) |
| Google | `GEMINI_API_KEY` | Gemini models, LLM judge |
| OpenAI | `OPENAI_API_KEY` | GPT models |
| Anthropic | `ANTHROPIC_API_KEY` | Claude models |

Set `ROOT_PATH` to the absolute path of the repository root.

### Training

Training runs the agentic system on the training split, dynamically creating tools:

```bash
# Basic training (questions 0-9)
uv run scripts/run_training_phase.py --start 0 --end 10

# Batched training (memory-safe, runs each batch as a separate process)
fish scripts/run_training_batched.fish --nb-samples 20 --batch-size 5

# Continue a previous run
uv run scripts/run_training_phase.py --start 10 --end 20 --continue <run-id>
```

### Evaluation

Evaluation runs one of several system configurations on the evaluation split:

```bash
# Agentic system with manual tools and context7 docs
uv run scripts/run_evaluation.py --start 0 --nb-samples 200 \
  --system cobbie --tools manual --doc context7

# Static one-shot baseline (no tools)
uv run scripts/run_evaluation.py --start 0 --nb-samples 200 --system static

# Batched evaluation (memory-safe)
fish scripts/run_eval_batched.fish --nb-samples 200 --batch-size 10
```

Key CLI arguments for `run_evaluation.py`:

| Argument | Options | Default | Description |
|---|---|---|---|
| `--system` | `cobbie`, `static`, `static-doc` | `cobbie` | QA system to evaluate |
| `--tools` | `initial`, `created`, `manual` | none | Tool directories to load (space-separated) |
| `--doc` | `custom`, `context7` | `custom` | Documentation backend |
| `--client` | `GLM_4_7`, etc. | `GLM_4_7` | LLM client |

### Evaluation Matrix

The paper reports results from 10 system configurations. Each is a separate MLflow run:

| Run Name | System | Tools | Docs | CLI Args |
|---|---|---|---|---|
| `dynamic-manual-doc` | cobbie | manual | context7 | `--system cobbie --tools manual --doc context7` |
| `dynamic-auto-doc` | cobbie | created | context7 | `--system cobbie --tools created --doc context7` |
| `dynamic-None-doc` | cobbie | -- | context7 | `--system cobbie --doc context7` |
| `dynamic-manual-no_doc` | cobbie | manual | custom | `--system cobbie --tools manual --doc custom` |
| `dynamic-auto-no_doc` | cobbie | created | custom | `--system cobbie --tools created --doc custom` |
| `dynamic-None-no_doc` | cobbie | -- | custom | `--system cobbie --doc custom` |
| `static-manual` | static | manual | -- | `--system static --tools manual` |
| `static-created` | static | created | -- | `--system static --tools created` |
| `static-None` | static | -- | -- | `--system static` |
| `static-doc` | static-doc | -- | custom | `--system static-doc --doc custom` |

### Analysis

After evaluation runs complete:

```bash
# Cross-run comparison and metrics
uv run scripts/analyze_evaluation_matrix.py

# Single-run detailed analysis
uv run scripts/analyze_evaluation_runs.py --run-ids <run-id>

# Interactive error analysis (Streamlit app)
uv run streamlit run scripts/eval_analysis_app.py
```

## Supported LLM Providers

The system supports multiple LLM providers via BAML client definitions:

- **Z.AI** (GLM-4.7) -- default for all experiments
- **OpenAI** (GPT models)
- **Anthropic** (Claude)
- **Google** (Gemini)
- **DeepSeek**, **Groq**, **Mistral**, **Fireworks**, **Cerebras**, **OpenRouter**

## Development

```bash
# Lint
uv run ruff check .

# Type check
uvx ty check

# Regenerate BAML client after editing baml_src/
cd src/baml && uv run baml-cli generate
```

## License

CC BY 4.0 -- see [LICENSE](LICENSE).
