# API Documentation

## Core Classes

### IfcAnswerEngine

The main engine for processing questions about IFC models.

```python
class IfcAnswerEngine(dspy.Module):
    def __init__(
        self,
        additional_authorized_functions: Optional[Dict[str, Callable]] = None,
        additional_authorized_imports: Optional[List[str]] = None,
        config: Optional[IfcAnswerEngineConfig] = None,
        llm: Optional[dspy.LM] = None,  # Optional override
    )

    def forward(self, question: str, path_ifc_model: str = "") -> ModuleOutput:
        """
        Process a question about an IFC model.

        Args:
            question: Natural language question about the BIM model
            path_ifc_model: Path to the .ifc file

        Returns:
            ModuleOutput with result containing answer or tool requirements
        """
```

### ToolCreator

Multi-agent system for creating new tools.

```python
class ToolCreator(dspy.Module):
    def __init__(
        self,
        additional_authorized_functions: Dict[str, Callable] = {...},
        config: Optional[ToolCreatorConfig] = None,
        callbacks=None,
        llm: Optional[dspy.LM] = None,  # Optional override
    )

    def forward(
        self,
        function_requirements: str,
        function_name: str,
        path_ifc_model: str,
    ) -> ModuleOutput:
        """
        Create a new tool based on requirements.

        Args:
            function_requirements: Description of what the function should do
            function_name: Name for the new function
            path_ifc_model: Path to IFC file for testing

        Returns:
            ModuleOutput with function implementation if successful
        """
```

### TrainingModule

Training pipeline for the system.

```python
class TrainingModule(dspy.Module):
    def __init__(
        self,
        config: Optional[TrainingModuleConfig] = None,
        lm: Optional[dspy.LM] = None,  # Optional override
    )

    def forward(self, datapoint: Datapoint) -> ModuleOutput:
        """
        Train on a single datapoint.

        Args:
            datapoint: Training example with question, answer, and model path

        Returns:
            ModuleOutput with training results
        """
```

## Configuration Classes

### IfcAnswerEngineConfig

```python
class IfcAnswerEngineConfig(BaseAgentConfig):
    max_iters: int = 10
    max_retry: int = 2
    import_all_created_tools: bool = True
    add_code_prefix: bool = True
    tool_creator: ToolCreatorConfig = Field(default_factory=ToolCreatorConfig)
```

### LLM config

see src/config/llm.py

## Utility Functions

### Configuration Management

```python
from src.config import update_config, get_config, AGENT_CONFIGS

# Update specific agent configuration
update_config('ifc_answer_engine', max_retry=5, log_level='INFO')

# Get configuration for an agent
config = get_config('tool_creator')

# Access global configurations
engine_config = AGENT_CONFIGS.ifc_answer_engine
```

### Tool Management

```python
from src.tools import get_created_tools
from src.engine.util import save_new_tool

# Get all dynamically created tools
tools = get_created_tools()

# Save a new tool
success = save_new_tool(
    function_name="my_function",
    function_implementation="def my_function(...):\n    ..."
)
```

## Data Models

### ModuleOutput

```python
class ModuleOutput(BaseModel):
    result: Result = Field(default_factory=Result)
    status: Literal["success", "error"] = "error"
    error_msg: Optional[str] = None
```

### Result

```python
class Result(BaseModel):
    answer: Optional[str] = None
    need_new_function: Optional[bool] = None
    function_requirements: Optional[str] = None
    function_name: Optional[str] = None
    function_implementation: Optional[str] = None
    new_function: Optional[Callable] = None
    assessment_status: Optional[Literal["ok", "needs_improvement"]] = None
    assessment_details: Optional[str] = None
    similarity_score: Optional[float] = None
```

### Datapoint

```python
class Datapoint(BaseModel):
    id: int
    question: str
    answer: str
    ifc_model_path: str
    ifc_id: Optional[int] = None
```

## Usage Examples

### Basic Question Answering

```python
from src.engine import IfcAnswerEngine

engine = IfcAnswerEngine()
result = engine.forward(
    question="What is the height of the building?",
    path_ifc_model="path/to/model.ifc"
)

if result.status == "success":
    print(f"Answer: {result.result.answer}")
    if result.result.need_new_function:
        print(f"New tool needed: {result.result.function_requirements}")
else:
    print(f"Error: {result.error_msg}")
```

### Custom Configuration

```python
from src.config.agents import IfcAnswerEngineConfig, LLMConfig

config = IfcAnswerEngineConfig(
    llm=LLMConfig(model_name="claude", max_tokens=32000),
    max_retry=3,
    log_level="DEBUG"
)

engine = IfcAnswerEngine(config=config)
```

### Training

```python
from src.experiment.training.training import TrainingModule
from src.experiment.datasets import load_train_dev_split

training = TrainingModule()
train, dev = load_train_dev_split()

for datapoint in train[:5]:  # Train on first 5 examples
    result = training.forward(datapoint)
    print(f"Question: {datapoint.question}")
    print(f"Status: {result.status}")
```
