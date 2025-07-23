# IfcAnswerEngine - V3

An intelligent engine that answers questions about BIM models in .ifc format using a sophisticated multi-agent system. Built with [DSPy](https://github.com/stanfordnlp/dspy) and featuring dynamic tool creation, the system can learn new capabilities during training and apply them in inference.

## 🚀 Key Features

- **Multi-Agent Architecture**: Specialized agents for different tasks (programming, assessment, correction)
- **Dynamic Tool Creation**: Automatically generates new Python functions when needed
- **Hierarchical Configuration**: Clean, type-safe configuration system with Pydantic
- **Training & Inference Modes**: Learn new tools during training, apply them during inference
- **MLflow Integration**: Complete experiment tracking and logging
- **Type Safety**: Full type hints and validation throughout the codebase

## 🏗️ System Architecture

### Core Components

The system is built around several specialized agents that work together:

```mermaid
graph TB
    subgraph "IfcAnswerEngine"
        IE[Main Engine]
        TC[ToolCreator]
        NE[NameExtractor]
    end
    
    subgraph "Multi-Agent Tool Creation"
        TP[ToolProgrammer]
        TA[ToolAssessor] 
        TCR[ToolCorrector]
    end
    
    subgraph "Configuration System"
        AC[AGENT_CONFIGS]
        LC[LLM Config]
        SC[Sub-Agent Configs]
    end
    
    subgraph "Tools & Execution"
        PT[Primordial Tools]
        CT[Created Tools]
        PI[Python Interpreter]
    end
    
    IE --> TC
    IE --> NE
    TC --> TP
    TC --> TA
    TC --> TCR
    AC --> IE
    AC --> TC
    LC --> AC
    SC --> AC
    PT --> TP
    CT --> IE
    PI --> TP
    PI --> TA
    PI --> TCR
```

### Agent Responsibilities

- **IfcAnswerEngine**: Main orchestrator that processes questions and coordinates other agents
- **ToolCreator**: Multi-agent system that creates new tools through iterative improvement
- **ToolProgrammer**: Generates initial function implementations using CodeAct
- **ToolAssessor**: Tests and evaluates generated functions through code execution
- **ToolCorrector**: Improves functions based on assessment feedback
- **NameExtractor**: Extracts function names from requirements

## 🔄 Training vs Inference Modes

### Training Mode

The system learns to create new tools when existing ones are insufficient:

```mermaid
flowchart TB
    Q[Question] --> IE[IfcAnswerEngine]
    IE --> TT{Try with existing tools}
    TT -->|Success| A[Answer]
    TT -->|Need new tool| NE[NameExtractor]
    NE --> TC[ToolCreator]
    
    subgraph "Tool Creation Pipeline"
        TC --> TP[ToolProgrammer<br/>Generate Code]
        TP --> TA[ToolAssessor<br/>Test & Evaluate]
        TA --> TCR[ToolCorrector<br/>Improve Code]
        TCR --> TA
        TA -->|Success| NT[New Tool]
    end
    
    NT --> IE
    IE --> A
    A --> AV[AnswerVerifier]
    AV -->|Correct + New Tool| ST[Save Tool]
    AV -->|Incorrect| TC
```

### Inference Mode

The system uses its trained toolset to answer questions efficiently:

```mermaid
flowchart TB
    Q[Question] --> IE[IfcAnswerEngine]
    IE --> ET[Existing Tools]
    IE --> PT[Primordial Tools<br/>• web_search<br/>• query_ifcopenshell_documentation]
    ET --> CA[CodeAct Agent]
    PT --> CA
    CA --> PI[Python Interpreter]
    PI --> A[Answer]
```

## ⚙️ Configuration System

The system uses a hierarchical configuration approach that eliminates parameter explosion:

### Simple Usage
```python
from src.engine import IfcAnswerEngine

# Clean initialization - everything comes from config!
engine = IfcAnswerEngine()
```

### Advanced Configuration
```python
from src.config import AGENT_CONFIGS, update_config
from src.config.agents import IfcAnswerEngineConfig, LLMConfig

# Update global configuration
update_config('ifc_answer_engine', max_retry=5, log_level='INFO')

# Or create custom configuration
custom_config = IfcAnswerEngineConfig(
    llm=LLMConfig(model_name="claude", max_tokens=32000),
    max_retry=3,
    log_level="DEBUG"
)
engine = IfcAnswerEngine(config=custom_config)
```

### Configuration Structure
```
src/config/
├── __init__.py          # Main exports
├── main.py             # Paths, API keys, models
└── agents.py           # Agent configurations
    ├── LLMConfig       # Language model settings  
    ├── BaseAgentConfig # Common agent settings
    ├── ToolCreatorConfig
    ├── IfcAnswerEngineConfig
    └── TrainingModuleConfig
```

## 📁 Project Structure

```
ifcAnswerEngineV3/
├── src/
│   ├── config/                    # Configuration system
│   │   ├── __init__.py
│   │   ├── main.py               # Core config (paths, models, etc.)
│   │   └── agents.py             # Agent configurations
│   │
│   ├── engine/                   # Main engine components
│   │   ├── __init__.py
│   │   ├── engine.py             # Main IfcAnswerEngine
│   │   ├── components/           # Agent implementations
│   │   │   ├── code_act.py       # CodeAct base agent
│   │   │   ├── tool_creator.py   # Multi-agent tool creation
│   │   │   ├── tool_programmer.py
│   │   │   ├── tool_assessor.py
│   │   │   ├── tool_corrector.py
│   │   │   └── extract_function_name.py
│   │   ├── schemas/              # Data models
│   │   │   ├── datapoint.py
│   │   │   ├── module_output.py
│   │   │   └── result.py
│   │   ├── tools/               # Tool management
│   │   │   ├── primordial/      # Built-in tools
│   │   │   ├── created/         # Dynamically created tools
│   │   │   └── get_created_tools.py
│   │   └── util/                # Utilities
│   │
│   └── experiment/              # Training and evaluation
│       ├── training/
│       │   ├── training.py      # Training pipeline
│       │   └── data_loader.py
│       ├── evaluation/
│       │   └── answer_verifier.py
│       └── db/                  # Database and datasets
│
├── examples/                    # Usage examples
│   └── config_usage.py
├── docs/                       # Documentation
│   └── configuration_migration_guide.md
└── README.md
```

## 🚀 Getting Started

### Prerequisites

- Python 3.12+
- `uv` package manager

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/sylvainhellin/ifcAnswerEngineV3.git
   cd ifcAnswerEngineV3
   ```

2. Create virtual environment and install dependencies:
   ```bash
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   uv pip install -e .
   ```

3. Set up environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

### Quick Start

#### Basic Usage
```python
from src.engine import IfcAnswerEngine

# Initialize with default configuration
engine = IfcAnswerEngine()

# Ask a question about an IFC model
result = engine.forward(
    question="What is the height of the living room?",
    path_ifc_model="path/to/your/model.ifc"
)

print(result.result.answer)
```

#### Training Mode
```python
from src.experiment.training.training import TrainingModule

# Initialize training module
training = TrainingModule()

# Train on a dataset
from src.experiment.training.data_loader import load_train_dev_split
train, dev = load_train_dev_split()

for datapoint in train:
    result = training.forward(datapoint)
    print(f"Status: {result.status}")
```

### MLflow Tracking

Start MLflow server for experiment tracking:
```bash
mlflow server --host 127.0.0.1 --port 5000 --backend-store-uri sqlite:///mlflow.sqlite
```

Access the UI at: http://127.0.0.1:5000

## 🔧 Configuration Options

### Language Models
The system supports multiple LLM providers configured in `src/config/main.py`:
- OpenAI (GPT models)
- Anthropic (Claude models) 
- Google (Gemini models)
- Groq (Llama models)
- Local models via Ollama

### Agent Configuration
Each agent can be individually configured:
```python
from src.config import update_config

# Configure engine behavior
update_config('ifc_answer_engine', max_retry=3, log_level='INFO')

# Configure tool creation
update_config('tool_creator', max_iter=5)

# Configure sub-agents
update_config('tool_programmer', max_iters=15)
```

## 🧪 Examples

See `examples/config_usage.py` for comprehensive configuration examples:
- Default configuration usage
- Global parameter overrides
- Custom configuration objects
- LLM configuration management

## 📚 Documentation

- [Configuration Migration Guide](docs/configuration_migration_guide.md) - Detailed guide on the new config system
- [API Documentation](docs/api.md) - Complete API reference (coming soon)
- [Training Guide](docs/training.md) - How to train the system (coming soon)

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🏷️ Version History

- **v3.0**: DSPy-based architecture with hierarchical configuration system
- **v2.0**: Multi-agent system with tool creation capabilities  
- **v1.0**: Initial implementation with basic question answering
