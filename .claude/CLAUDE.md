# CLAUDE.md

> **Note:** This repo was moved on 2025-01-19.
> Old path: `~/GitHub/4_phd/cobbie`
> New path: `~/code/tum/cobbie`
> If something breaks due to hardcoded paths, this might be the cause.

## Build & Test Commands

### Backend (Python)
- **Lint**: `uv run ruff check .`
- **Type Check**: `uvx ty check`

### MLflow Tracking
- **Start MLflow**: `uv run mlflow server --host 127.0.0.1 --port 5000 --backend-store-uri sqlite:///mlflow.sqlite --uvicorn-opts "--timeout=120 -w 1"`
  - **Important**: Use single worker (`-w 1`) to avoid SQLite database locking issues with concurrent writes
  - The `--timeout=120` option prevents timeouts for long-running operations

### Training & Evaluation
- **Training**: `uv run scripts/run_training_phase.py --start 0 --end 10`
- **Evaluation**: `uv run scripts/run_evaluation.py --start 0 --nb-samples 5`

## Architecture Overview

This is a sophisticated AI System named Cobbie (COde Based BIM Information Extraction) for BIM Information Extraction, using an LLM-based multi-agent architecture. The system supports both training and inference modes, with dynamic tool creation capabilities during training to answer questions about IFC (Industry Foundation Classes) building models.


### Core Components
- **Main Agents**: `src/agents/cobbie.py` (primary BIM extraction), `src/agents/answer_verifier.py`
- **Tool Ecosystem**: `src/tools/initial/` (base tools) and `src/tools/created/` (dynamically generated)
- **BAML**: `src/baml/baml_src/` (source) and `src/baml/baml_client/` (auto-generated). Regenerate with `cd src/baml && uv run baml-cli generate`
- **Data Pipeline**: SQLite database with MLflow tracking
- **Web Interface**: See [cobbie-web](../cobbie-web) for FastAPI backend and React frontend


## Development Notes

### Environment Setup
- Python 3.12+ required
- Uses `uv` package manager - all Python commands should use `uv run` prefix
- Requires multiple API keys for LLM providers (set in `.env`)
- MLflow server required for training/evaluation tracking

### Database Integration
- SQLite database (`db.db`) stores IFC model metadata and QA pairs
- **IFC Models table**: `ifcmodels` - contains project metadata and file paths
- **QA Dataset table**: `ifc_bench` - contains questions, ground truth answers, and categories
- **Tool Usage Stats table**: `tool_usage_stats` - tracks tool metrics for management system
- All database operations use SQLModel ORM with `Session(db.ENGINE)` pattern
- Schema changes require regenerating models: `uv run sqlacodegen sqlite:///src/db/db.db --generator sqlmodels --outfile src/db/models.py`
- All queries must be in `src/db/query.py` (not separate util files)
- NocoDB can be used for visual database interaction (runs on port 8080)
- MLflow for experiment tracking and model performance monitoring

### Key Workflows
1. **Development**: Start MLflow, then use cobbie-web for API and web interface
2. **Training**: Use training scripts with configurable models, batch processing, and resume capabilities
3. **Evaluation**: Run evaluation scripts with comprehensive metrics and MLflow tracking
4. **Tool Management**: Tools are dynamically created during training and persisted for inference

### IFC File Handling
- System works with .ifc files (BIM model format)
- IFC models registered in SQLite database (`ifcmodels` table)
- File paths stored in database reference actual .ifc files
- Test models available in `src/db/bim_models/`

### Multi-LLM Support
The system supports multiple LLM providers:
- Z.AI (GLM-4.7), OpenAI (GPT models), Anthropic (Claude)
- Google (Gemini), DeepSeek, Groq, Mistral, Fireworks, Cerebras, OpenRouter

### State Management
- Training uses sophisticated state machine with tool creation/correction/merging
- Comprehensive MLflow integration with nested span hierarchies
- Token usage tracking and cost analysis

## Important Guidelines
- Use `uv run` prefix for all Python commands
- Start MLflow server before training/evaluation
- Use BAML components for new development
- Use `uvx ty check <relative_path_to_file>` (e.g. `uvx ty check src/agents/cobbie.py`) to check for type errors whenever you implement something, before claiming it is finished.

## Code review
Before stating that you are done, you need to review each file you create or change, using the following tools: ruff, ty and pyright. You can use them together in a single command, as shown below:

```bash
uvx ruff check {relative_path_to_file}
uvx ty check {relative_path_to_file}
uvx pyright {relative_path_to_file}
```

## Access to documentation for modules or libraries.
You have a basic knowledge of most of the libraries and modules that we use here (e.g. BAML, MLFlow and SQLModel), but you are not aware of the latest developments in their respective APIs.
To address this, you should use context7. Ideally, you should do this before writing any code to ensure that you are using the correct API, or at least do so if you encounter any kind of syntax error.

### Context7 Libraries:
- mlflow:
  - name: "/mlflow/mlflow"
  - example usage: `context7 - query-docs (MCP)(context7CompatibleLibraryID: "/mlflow/mlflow", topic: "start_run continuation tracking", tokens: 2048)`
- baml:
  - name: "/websites/bourdaryml"
  - example usage: `context7 - query-docs (MCP)(context7CompatibleLibraryID: "/websites/boundaryml", topic: "use another client for test function", tokens: 2048)`

## Assumptions
Don't make any assumptions ; ask for clarifications if anything is unclear.
I would much rather you asked questions up front than made decisions on your own without knowing the full context.

## Writing guidelines

**IMPORTANT**

- Keep your responses and plans concise. Be brief and to the point, but make sure you include all the important information, especially the assumptions.
- The same applies when writing code. Write robust code, but remember that this is not a production-grade application, so there is no need to be overly defensive. Write code that is easy to understand, review and maintain.
