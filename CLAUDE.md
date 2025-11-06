# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Test Commands

### Backend (Python)
- **Dev Server**: `uv run python api/start_server.py` or `uv run uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload`
- **Lint**: `uv run ruff check .`
- **Type Check**: `uv run mypy .`

### MLflow Tracking
- **Start MLflow**: `uv run mlflow server --host 127.0.0.1 --port 5000 --backend-store-uri sqlite:///mlflow.sqlite`

### Training & Evaluation
- **Training**: `uv run scripts/run_training.py --model glm-4.6 --provider zai --no-cache`
- **Batch training**: `uv run scripts/run_training.py --model glm-4.6 --provider zai --batch-size 30`
- **Evaluation**: `uv run scripts/run_evaluation.py --start 0 --nb-samples 5`

### Testing
- **Specific test**: `uv run python test/test_cobbie.py`

## Architecture Overview

This is a sophisticated AI System named Cobbie (COde Based BIM Information Extraction) for BIM Information Extraction, using an LLM-based multi-agent architecture. The system supports both training and inference modes, with dynamic tool creation capabilities during training to answer questions about IFC (Industry Foundation Classes) building models.

### Dual Framework Architecture
The project is migrating from DSPy to BAML:
- **Legacy DSPy**: Located in `src/engine/components/` (OOP-based agents)
- **Current BAML**: Located in `src/agents/` and `baml_src/` (functional agents)

### Core Components
- **Main Agents**: `src/agents/cobbie.py` (primary BIM extraction), `src/agents/answer_verifier.py`
- **Tool Ecosystem**: `src.tools.initial/` (base tools) and `src.tools/created/` (dynamically generated)
- **Web API**: FastAPI application in `api/main.py` with dual engine support (DSPy/BAML)
- **Configuration**: Hierarchical config system in `src/config/` (for the legacy DSPy implementation ; not used for new BAML implementation)
- **Data Pipeline**: SQLite database with MLflow tracking


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
- NocoDB can be used for visual database interaction (runs on port 8080)
- MLflow for experiment tracking and model performance monitoring

### Key Workflows
1. **Development**: Start MLflow, then API server, then use web interface or API endpoints
2. **Training**: Use training scripts with configurable models, batch processing, and resume capabilities
3. **Evaluation**: Run evaluation scripts with comprehensive metrics and MLflow tracking
4. **Tool Management**: Tools are dynamically created during training and persisted for inference

### IFC File Handling
- System works with .ifc files (BIM model format)
- IFC models registered in SQLite database (`ifcmodels` table)
- File paths stored in database reference actual .ifc files
- Test models available in `src/experiment/bim_models/`

### Multi-LLM Support
The system supports multiple LLM providers:
- Z.AI (GLM-4.6), OpenAI (GPT models), Anthropic (Claude)
- Google (Gemini), DeepSeek, Groq, Mistral, Fireworks, Cerebras, OpenRouter

### State Management
- Training uses sophisticated state machine with tool creation/correction/merging
- Comprehensive MLflow integration with nested span hierarchies
- Token usage tracking and cost analysis

## Important Guidelines
- Use `uv run` prefix for all Python commands
- Start MLflow server before training/evaluation
- Use BAML components for new development (not DSPy)
- API supports both engines via environment variable configuration
- Use mypy to check for type errors whenever you implement something, before claiming it is finished.
