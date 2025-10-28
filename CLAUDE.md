# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Test Commands

### Backend (Python)
- **Dev Server**: `uv run python api/start_server.py` or `uv run uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload`
- **Test All**: `uv run pytest`
- **Single Test**: `uv run pytest tests/test_file.py::test_function`
- **Lint**: `uv run ruff check .`
- **Type Check**: `uv run mypy .`

### Engine Selection
- **DSPy Engine**: Default engine using `IfcAnswerEngine` (set `ENGINE_TYPE=dspy`)
- **BAML Engine**: Alternative engine using `BIMQASEngine` (set `ENGINE_TYPE=baml`)
- **Environment Variable**: `export ENGINE_TYPE=baml` to use BAML engine

### Frontend (React/TypeScript)
- **Dev Mode**: `cd frontend && pnpm run dev`
- **Build**: `cd frontend && pnpm run build`
- **Build (Dev)**: `cd frontend && pnpm run build:dev`
- **Lint**: `cd frontend && pnpm run lint`
- **Preview**: `cd frontend && pnpm run preview`

### MLflow Tracking
- **Start MLflow**: `uv run mlflow server --host 127.0.0.1 --port 5000 --backend-store-uri sqlite:///mlflow.sqlite`

## Architecture Overview

This is a sophisticated BIM AI question-answering system with a multi-agent architecture. The system can dynamically create Python tools to answer questions about IFC (Industry Foundation Classes) building models.

### Core Components

**Backend Architecture**:
- **Dual Engine System**: Two interchangeable engines with identical interfaces
  - `IfcAnswerEngine` (`src/engine/engine.py`): DSPy-based engine (original implementation)
  - `BIMQASEngine` (`src/engine/engine.py`): BAML-based engine (new implementation using Z.AI GLM-4.6)
- **Engine Factory**: `create_engine()` function for instantiating the appropriate engine based on configuration
- **Configurable Selection**: Choose engine type via `IfcAnswerEngineConfig.engine_type` or `ENGINE_TYPE` environment variable
- Multi-agent system with specialized roles:
  - `ToolCreatorBAML`: Creates new Python functions dynamically when existing tools are insufficient (BAML implementation)
  - `TestAndImproveBAML`: Tests and improves generated functions through iterative assessment and correction (BAML implementation)
  - `ToolAssessor`: Tests and validates generated functions (BAML component within TestAndImproveBAML)
  - `ToolCorrector`: Improves functions based on assessment feedback (BAML component within TestAndImproveBAML)
  - `CodeCleaner`: Fixes syntax and compilation errors (BAML component within TestAndImproveBAML)
  - `AnswerVerifier`: Compares AI answers with ground truth using similarity scoring
- `TrainingModule`: State machine for training mode that learns new tools through iterative improvement
- Configuration system with hierarchical Pydantic models in `src/config/`

**Engine Comparison**:
- **DSPy Engine**: Uses multiple LLM providers, supports optimization and compilation, extensive ecosystem
- **BAML Engine**: Uses Z.AI GLM-4.6 with Coding Plan, simplified architecture, comprehensive MLflow tracing
- **Interface Compatibility**: Both engines implement identical `forward(question, path_ifc_model) -> ModuleOutput` interface
- **Migration Strategy**: Gradual transition with configurable engine selection for A/B testing

**Agent Configuration Pattern**:
- **BAML Components**: Use `run_baml_function_with_metrics()` wrapper with comprehensive MLflow tracking
- **DSPy Components**: Use `dspy.context(lm=self.lm, adapter=self.config.llm.adapter)` for local configuration
- This hybrid approach allows each agent to maintain independent configurations without affecting others
- Configuration hierarchy: Base agent config → specialized agent configs → LLM settings per agent

### Key Directories

- `src/engine/`: Core AI engine components
  - `components/`: Multi-agent implementations (mix of BAML and DSPy)
    - **BAML Components**: `tool_creator_baml.py`, `test_and_improve_baml.py` (2 migrated)
    - **DSPy Components**: `engine.py`, `code_act.py`, `training_module.py`, `answer_verifier.py`, `tool_assessor.py`, `tool_corrector.py`, `tool_optimizer.py`, `tool_merger.py`, `error_analyst.py`, `tool_debugger.py` (13+ not migrated)
  - `tools/primordial/`: Built-in tools (web search, IFC documentation query)
  - `tools/created/`: Dynamically generated Python tools
  - `schemas/`: Pydantic data models for various operations
  - `util/`: Utilities including BAML common patterns (`baml_common.py`)
- `src/experiment/`: Training pipeline, evaluation, and database operations
  - `training/`: DSPy-based training pipeline (needs migration)
- `baml_src/`: BAML schema definitions (partial)
  - **Migrated**: `tool_creator.baml`, `test_and_improve.baml`
  - **Needed**: schemas for 13+ remaining components
- `baml_client/`: BAML client integration code
- `scripts/`: Training scripts (need BAML updates)
- `api/`: FastAPI web server with endpoints for questioning and model management
- `test/`: Test suites including BAML component tests (partial)

### Configuration System

The system uses a hierarchical configuration approach centered in `src/config/`:
- Environment variables and paths in `main.py`
- Agent configurations with LLM settings in `agents.py`
- Type-safe configuration with Pydantic models
- Support for multiple LLM providers (OpenAI, Anthropic, Google, Groq, local models via Ollama)

**Hybrid Configuration Pattern**:
- **BAML Components**: Use `run_baml_function_with_metrics()` wrapper with comprehensive MLflow tracking and union type flow control
- **DSPy Components**: Use `with dspy.context(lm=self.lm, adapter=self.config.llm.adapter):` for local configuration
- This hybrid approach prevents configuration conflicts between different component types
- Each sub-component can have different LLM providers, models, and settings
- Configuration is scoped to the context block, ensuring isolation between components

### Tool System

The system can dynamically create Python tools that:
- Use ifcopenshell library to analyze BIM models
- Extract geometric information, material properties, spatial relationships
- Perform calculations (areas, volumes, quantities)
- Search and filter building elements by various criteria

**BAML Tool Creation Pipeline**:
- **ToolCreatorBAML**: Creates initial function implementations using CodeAct pattern with union types
- **TestAndImproveBAML**: Iteratively tests and improves functions through assessment and correction cycles
- **Components**: ToolAssessor (black-box testing), ToolCorrector (targeted improvements), CodeCleaner (syntax fixes)
- **Integration**: Complete end-to-end BAML pipeline with comprehensive MLflow tracing

Created tools are persisted as `.py` files in `src/engine/tools/created/` and can be used in future sessions.

## Development Notes

### Environment Setup
- Python 3.12+ required
- Uses `uv` package manager for Python dependencies - all Python commands should use `uv run` prefix
- Requires multiple API keys for different LLM providers (set in `.env`)

### Database Integration
- SQLite database for storing IFC model metadata and question-answer pairs
- NocoDB can be used for visual database interaction (runs on port 8080)
- MLflow for experiment tracking and model performance monitoring

### IFC File Handling
- System works with .ifc files (BIM model format)
- Test models available in `src/experiment/bim_models/`
- Frontend (other repository) downloads IFC files from backend for 3D visualization

### Testing and Validation
- Built-in answer verification using classification-based evaluation (correct/wrong/abstained)
- Comprehensive error analysis and categorization
- Tool optimization through merging and correction processes
- **BAML Testing**: Comprehensive test suites for BAML components with MLflow integration
  - `test/test_tool_creator_baml.py`: End-to-end BAML pipeline testing
  - `test/test_and_improve_baml_test.py`: Component-level BAML testing
- **Function Accessibility**: Dynamic function injection for CodeAct execution context

## BAML Integration Status

### Current Progress: ~80% Complete
**Status**: ENGINE INTEGRATED - BAML engine now available as drop-in replacement

### ✅ Successfully Integrated (Major Components)
- **BIMQASEngine**: `src/engine/engine.py` - Complete BAML-based alternative to IfcAnswerEngine
- **Engine Factory**: `create_engine()` function for configurable engine selection
- **Interface Compatibility**: Identical `forward(question, path_ifc_model) -> ModuleOutput` interface
- **Configuration System**: Engine type selection via `IfcAnswerEngineConfig.engine_type`
- **API Integration**: Engine selection via `ENGINE_TYPE` environment variable
- **Pipeline Integration**: Training and evaluation pipelines support both engines
- **BAML Components**: `ToolCreatorBAML`, `TestAndImproveBAML` (previously migrated)

### 🔧 Configuration Options
- **Default Engine**: DSPy (`IfcAnswerEngine`) for backward compatibility
- **BAML Engine**: Set `ENGINE_TYPE=baml` or `config.engine_type="baml"`
- **Factory Usage**: `engine = create_engine(engine_type="baml")`

### 🚀 Usage Examples
```python
# Via environment variable
export ENGINE_TYPE=baml
uv run python api/start_server.py

# Via configuration
from src.engine import create_engine
engine = create_engine(engine_type="baml")
result = engine.forward(question="How many windows?", path_ifc_model="model.ifc")
```

### ❌ Still DSPy-Only Components (Optional Migration)
The following components remain DSPy-based but are fully functional:
- **CodeAct**: Core code execution (BAML uses different approach)
- **TrainingModule**: Training state machine (DSPy-specific optimization)
- **Tool Chain**: ToolAssessor, ToolCorrector, etc. (AnswerVerifier migrated to BAML)
- **Optimization**: MIPRO, Bootstrap optimizers (DSPy-specific)

#### **Tool Chain Components**
- **AnswerVerifier**: `src/engine/components/answer_verifier.py` - DSPy similarity scoring (legacy)
- **BamlAnswerVerifier**: `src/engine/components/baml_answer_verifier.py` - BAML classification-based evaluation
- **ToolAssessor**: `src/engine/components/tool_assessor.py` - Black-box testing
- **ToolCorrector**: `src/engine/components/tool_corrector.py` - Function improvement
- **ToolOptimizer**: `src/engine/components/tool_optimizer.py` - Tool analysis
- **ToolMerger**: `src/engine/components/tool_merger.py` - Function merging

#### **Analysis & Debugging Components**
- **ErrorAnalyst**: `src/engine/components/error_analyst.py` - Error categorization
- **ToolDebugger**: `src/engine/components/tool_debugger.py` - Tool debugging
- **NameExtractor**: `src/engine/components/extract_function_name.py` - Function name extraction
- **ToolIdentifier**: `src/engine/components/tool_identifier.py` - Tool identification

#### **Training & Pipeline Components**
- **TrainingPipeline**: `src/experiment/training/training_pipeline.py` - Full training workflow
- **Training Scripts**: `scripts/run_training.py`, `scripts/run_training_batch.py`

### Migration Architecture Benefits
- **Enhanced Observability**: Comprehensive MLflow tracing with actual parameters
- **Clean Union Types**: `CodeAction | ResultType` flow control instead of complex state management
- **Direct Token Tracking**: BAML Collector API for direct token usage monitoring
- **Improved Performance**: Reduced iterations and cleaner execution patterns

### Documentation & Planning
- **Migration Plan**: See `migration_plan.md` for detailed implementation strategy
- **Status Tracking**: See `DSL_TO_BAML_MIGRATION_STATUS.md` and `BAML_MIGRATION_SUMMARY.md`
- **Implementation Pattern**: Union types with `isinstance()` checking for flow control

## Guidelines for writing and testing code
- Always use `uv run` to execute a python script
- Always save test scripts in the `/test` directory to keep them organized and separate from production code
- Always use context7 when I need code generation, setup or configuration steps, or
library/API documentation. This means you should automatically use the Context7 MCP
tools to resolve library id and get library docs without me having to explicitly ask. This is especially true when interacting the the following libraries:
  - mlflow
  - dspy
  - baml
  - fastapi
  - sqlmodel

### BAML Development Guidelines
- **Migration Pattern**: Use established patterns from `src/engine/util/baml_common.py` for new BAML components
- **Union Types**: Follow `CodeAction | ResultType` pattern for clean flow control
- **MLflow Integration**: Always use `run_baml_function_with_metrics()` wrapper
- **Function Integration**: Ensure dynamically created functions are properly added to Python interpreter context
- **Schema Design**: Create BAML schemas in `baml_src/` following existing patterns
- **Client Generation**: Run `uv run baml-cli generate` after schema changes

### DSPy to BAML Migration Workflow
- **Phase 1**: Create BAML schemas for each DSPy component
- **Phase 2**: Implement BAML version using union types
- **Phase 3**: Replace DSPy calls with BAML calls
- **Phase 4**: Update configuration and integration
- **Phase 5**: Test and validate migration

### Migration Priority Order
1. **Core Engine**: IfcAnswerEngine, CodeAct, TrainingModule
2. **Tool Chain**: AnswerVerifier, ToolAssessor, ToolCorrector, ToolOptimizer
3. **Analysis**: ErrorAnalyst, ToolDebugger, supporting components
4. **Training**: TrainingPipeline, training scripts
5. **Integration**: Update main orchestration and configuration

- Don't make any assumptions. If anything is unclear, ask for clarification.
- If you create new tests, unless explicitly stated differently, don't create a new mlflow experiment: use the "test" experiment.
