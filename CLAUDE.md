# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Test Commands

### Backend (Python)
- **Dev Server**: `uv run python api/start_server.py` or `uv run uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload`
- **Test All**: `uv run pytest`
- **Single Test**: `uv run pytest tests/test_file.py::test_function`
- **Lint**: `uv run ruff check .`
- **Type Check**: `uv run mypy .`

### Frontend (React/TypeScript)
- **Dev Mode**: `cd frontend && pnpm run dev`
- **Build**: `cd frontend && pnpm run build`
- **Build (Dev)**: `cd frontend && pnpm run build:dev`
- **Lint**: `cd frontend && pnpm run lint`
- **Preview**: `cd frontend && pnpm run preview`

### MLflow Tracking
- **Start MLflow**: `uv run mlflow server --host 127.0.0.1 --port 5000 --backend-store-uri sqlite:///mlflow.sqlite`

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

**Agent Configuration Pattern**:
- Each sub-agent has its own configuration (e.g., `ToolCreatorConfig`, `ToolAssessorConfig`) with specific LLM settings
- Uses `dspy.context(lm=self.lm, adapter=self.config.llm.adapter)` instead of global `dspy.configure(lm=lm)`
- This approach allows each agent to maintain independent LM configurations without affecting others
- Configuration hierarchy: Base agent config → specialized agent configs → LLM settings per agent

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

**DSPy Configuration Pattern**:
- Each agent uses `with dspy.context(lm=self.lm, adapter=self.config.llm.adapter):` for local configuration
- Avoids global `dspy.configure(lm=lm)` to prevent configuration conflicts between agents
- Each sub-agent can have different LLM providers, models, and settings
- Configuration is scoped to the context block, ensuring isolation between agents

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
- Uses `uv` package manager for Python dependencies - all Python commands should use `uv run` prefix
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