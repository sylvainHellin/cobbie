# Cobbie - Code-Based BIM Information Extraction

An AI Agent for answering questions about BIM models in IFC format using a multi-agent architecture with dynamic tool creation.

## Features

- **Dynamic IFC Model Exploration**: Intelligent navigation and querying of BIM models in IFC format
- **Multi-Agent Architecture**: Specialized agents for programming, assessment, and correction tasks
- **Automated Tool Creation**: Dynamically generates Python functions during training for reuse in inference
- **MLflow Integration**: Complete experiment tracking and logging

## Quick Start

### Prerequisites

- Python 3.12+
- `uv` package manager

### Installation

```bash
git clone <repository-url>
cd cobbie
uv sync
cp .env.example .env  # Edit with your API keys
```

## Start the Services

### MLflow Tracking

```bash
uv run mlflow server --host 127.0.0.1 --port 5000 \
  --backend-store-uri sqlite:///$(pwd)/.mlflow/mlflow.sqlite \
  --default-artifact-root $(pwd)/.mlflow/mlartifacts \
  --gunicorn-opts "--timeout=120 -w 1"
```

Access the UI at: http://127.0.0.1:5000

### Web Interface

The FastAPI backend and React frontend are in the [cobbie-web](../cobbie-web) repository.

## Project Structure

```
cobbie/
├── baml_src/             # BAML agent definitions
├── baml_client/          # Generated BAML client (auto-generated)
├── src/
│   ├── agents/           # Multi-agent implementations
│   ├── baseline/         # Baseline implementations for comparison
│   ├── db/               # Database layer and IFC models
│   ├── docs_indexer/     # Documentation retrieval (RAG)
│   │   └── external/     # IfcOpenShell documentation (submodule)
│   ├── schemas/          # Pydantic data models
│   ├── tools/            # Tool ecosystem
│   │   ├── initial/      # Base tools (docs query, web search)
│   │   ├── created/      # Dynamically generated tools
│   │   └── manual/       # Manually curated tools
│   └── util/             # Utilities (metrics, execution, etc.)
├── scripts/              # Training and evaluation scripts
├── outputs/              # Generated reports, figures, cache
└── .mlflow/              # MLflow tracking data
```

## Training & Evaluation

```bash
# Training
uv run scripts/run_training_phase.py --start 0 --end 10

# Evaluation
uv run scripts/run_evaluation.py --start 0 --nb-samples 5

# Analyze results
uv run scripts/analyze_evaluation_runs.py --run-ids <run_id>
uv run scripts/analyze_evaluation_runs.py --run-ids <run_id> --export my_analysis
```

## Development

```bash
# Lint
uv run ruff check .

# Type check
uvx ty check
```

## License

MIT License
