# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Test Commands

### Backend (Python)
- **Dev Server**: `python api/start_server.py` or `uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload`
- **Test All**: `pytest`
- **Single Test**: `pytest tests/test_file.py::test_function`
- **Lint**: `ruff check .`
- **Type Check**: `mypy .`

### Frontend (React/TypeScript)
- **Dev Mode**: `cd frontend && pnpm run dev`
- **Build**: `cd frontend && pnpm run build`
- **Build (Dev)**: `cd frontend && pnpm run build:dev`
- **Lint**: `cd frontend && pnpm run lint`
- **Preview**: `cd frontend && pnpm run preview`

### MLflow Tracking
- **Start MLflow**: `mlflow server --host 127.0.0.1 --port 5000 --backend-store-uri sqlite:///mlflow.sqlite`

## Architecture Overview

This is a sophisticated BIM AI question-answering system with a multi-agent architecture built on DSPy. The system can dynamically create Python tools to answer questions about IFC (Industry Foundation Classes) building models.

### Core Components

**Backend Architecture**:
- `IfcAnswerEngine` (`src/engine/engine.py`): Main orchestrator that processes natural language questions about BIM models
- Multi-agent system with specialized roles:
  - `ToolCreator`: Creates new Python functions dynamically when existing tools are insufficient
  - `ToolProgrammer`: Generates initial function implementations using CodeAct
  - `ToolAssessor`: Tests and validates generated functions
  - `ToolCorrector`: Improves functions based on feedback
  - `AnswerVerifier`: Compares AI answers with ground truth using similarity scoring
- `TrainingModule`: State machine for training mode that learns new tools through iterative improvement
- Configuration system with hierarchical Pydantic models in `src/config/`

**Frontend Architecture**:
- React + TypeScript with Vite build system
- Uses "@thatopen" components for 3D IFC model visualization
- Shadcn/ui component library for interface elements
- Supabase for potential backend integration
- BIM viewer renders IFC models using web-ifc and related 3D libraries

**Data Flow**:
1. User selects BIM model and asks question via frontend
2. FastAPI backend (`api/main.py`) receives request and loads IFC model
3. `IfcAnswerEngine` processes question using available tools (both primordial and created)
4. If needed, dynamically generates new Python tools to answer the question
5. Returns answer to frontend, with option to highlight relevant model elements

### Key Directories

- `src/engine/`: Core AI engine components
  - `components/`: Multi-agent implementations (tool_creator, tool_assessor, etc.)
  - `tools/primordial/`: Built-in tools (web search, IFC documentation query)
  - `tools/created/`: Dynamically generated Python tools
  - `schemas/`: Pydantic data models for various operations
- `src/experiment/`: Training pipeline, evaluation, and database operations
- `api/`: FastAPI web server with endpoints for questioning and model management
- `frontend/`: React application with 3D BIM viewer and chat interface

### Configuration System

The system uses a hierarchical configuration approach centered in `src/config/`:
- Environment variables and paths in `main.py`
- Agent configurations with LLM settings in `agents.py`
- Type-safe configuration with Pydantic models
- Support for multiple LLM providers (OpenAI, Anthropic, Google, Groq, local models via Ollama)

### Tool System

The system can dynamically create Python tools that:
- Use ifcopenshell library to analyze BIM models
- Extract geometric information, material properties, spatial relationships
- Perform calculations (areas, volumes, quantities)
- Search and filter building elements by various criteria

Created tools are persisted as `.py` files in `src/engine/tools/created/` and can be used in future sessions.

## Development Notes

### Environment Setup
- Python 3.12+ required
- Uses `uv` package manager for Python dependencies
- Frontend uses `pnpm` package manager
- Requires multiple API keys for different LLM providers (set in `.env`)

### Database Integration
- SQLite database for storing IFC model metadata and question-answer pairs
- NocoDB can be used for visual database interaction (runs on port 8080)
- MLflow for experiment tracking and model performance monitoring

### IFC File Handling
- System works with .ifc files (BIM model format)
- Test models available in `src/experiment/bim_models/`
- Frontend downloads IFC files from backend for 3D visualization

### Testing and Validation
- Built-in answer verification using similarity scoring
- Comprehensive error analysis and categorization
- Tool optimization through merging and correction processes