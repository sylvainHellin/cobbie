# Configuration System Migration Guide

## Overview

This guide explains the migration from the old parameter-heavy initialization system to the new hierarchical configuration system.

## Problem with Old System

**Before:**
```python
# Too many parameters passed through multiple levels
engine = IfcAnswerEngine(
    llm=llm,
    max_iters=10,
    max_retry=2,
    log_level="DEBUG",
    max_tokens_logs=2**12,
    max_tokens_output=2**12,
    import_all_created_tools=True,
    max_iter_tool_creator=3,
    max_iter_sub_agents_tool_creator=10,
    add_code_prefix=True,
)

# Parameters had to be passed down to sub-agents
tool_creator = ToolCreator(
    llm=llm,
    max_iter=3,
    max_iter_sub_agents=10,
    log_level="DEBUG",
    add_code_prefix=True,
)
```

**Issues:**
- 11+ parameters for IfcAnswerEngine
- Parameter passing through multiple levels
- Difficult to maintain and modify
- No type safety
- Hard to understand relationships between configs

## New Configuration System

**After:**
```python
# Clean initialization with defaults
engine = IfcAnswerEngine(llm=llm)

# Or with custom config
engine = IfcAnswerEngine(llm=llm, config=custom_config)
```

### Architecture

```
src/config/
├── __init__.py          # Main exports
├── main.py             # Original config (paths, LLMs, etc.)
└── agents.py           # New agent configurations
```

## Key Benefits

### 1. **Hierarchical Configuration**
```python
from src.config import AGENT_CONFIGS

# Access nested configurations
engine_config = AGENT_CONFIGS.ifc_answer_engine
tool_creator_config = engine_config.tool_creator
programmer_config = tool_creator_config.tool_programmer
```

### 2. **Type Safety with Pydantic**
```python
class IfcAnswerEngineConfig(BaseAgentConfig):
    max_iters: int = Field(default=10, description="Maximum iterations")
    max_retry: int = Field(default=2, description="Maximum retry attempts")
    # ... other fields with validation
```

### 3. **Easy Parameter Updates**
```python
from src.config import update_config

# Update specific parameters globally
update_config('ifc_answer_engine', max_retry=5, log_level='INFO')
update_config('tool_creator', max_iter=5)
```

### 4. **Custom Configurations**
```python
from src.config.agents import IfcAnswerEngineConfig, ToolCreatorConfig

# Create completely custom configs
custom_config = IfcAnswerEngineConfig(
    max_iters=15,
    max_retry=3,
    log_level="WARNING",
    tool_creator=ToolCreatorConfig(max_iter=2)
)

engine = IfcAnswerEngine(llm=llm, config=custom_config)
```

## Migration Steps

### Step 1: Update Imports
```python
# Old
from src.config import LANGUAGE_MODELS, LOG_LEVEL

# New
from src.config import AGENT_CONFIGS, LANGUAGE_MODELS, LOG_LEVEL
```

### Step 2: Simplify Initialization

**Old IfcAnswerEngine:**
```python
engine = IfcAnswerEngine(
    llm=llm,
    max_iters=10,
    max_retry=2,
    log_level="DEBUG",
    max_tokens_logs=2**12,
    max_tokens_output=2**12,
    import_all_created_tools=True,
    max_iter_tool_creator=3,
    max_iter_sub_agents_tool_creator=10,
    add_code_prefix=True,
)
```

**New IfcAnswerEngine:**
```python
# With defaults
engine = IfcAnswerEngine(llm=llm)

# Or with custom config
engine = IfcAnswerEngine(llm=llm, config=custom_config)
```

**Old TrainingModule:**
```python
training_module = TrainingModule(
    lm=llm,
    log_level="DEBUG",
    training_size=2,
    similarity_treshold=0.8,
    add_code_prefix=True,
    max_retry_engine=2,
    max_iter_engine=10,
    max_tokens_logs=2**12,
    max_tokens_outputs=2**12,
    import_all_created_tools=True,
    tracking_uri="http://127.0.0.1:5000",
    experiment_name="Training"
)
```

**New TrainingModule:**
```python
# Much cleaner!
training_module = TrainingModule(lm=llm)
```

### Step 3: Update Sub-Agent Instantiation

**Old ToolCreator:**
```python
# Manual parameter passing to sub-agents
self.tool_programmer = ToolProgrammer(
    tools=self.primordial_tools,
    max_iters=self.max_iter_sub_agents,
    log_level=self.log_level,
    add_code_prefix=self.add_code_prefix,
)
```

**New ToolCreator:**
```python
# Sub-agents use their own configs automatically
self.tool_programmer = ToolProgrammer(
    tools=self.primordial_tools,
    config=self.config.tool_programmer,
)
```

## Configuration Files Structure

### Base Classes
- `BaseAgentConfig`: Common fields (log_level, max_tokens_*)
- `CodeActConfig`: CodeAct-specific fields (max_iters, add_code_prefix)

### Agent-Specific Classes
- `ToolProgrammerConfig`
- `ToolAssessorConfig`
- `ToolCorrectorConfig`
- `ToolCreatorConfig`
- `IfcAnswerEngineConfig`
- `TrainingModuleConfig`

### Global Container
- `AgentConfigs`: Contains all agent configurations
- `AGENT_CONFIGS`: Global instance with defaults

## Common Use Cases

### 1. Development with Debug Logging
```python
update_config('ifc_answer_engine', log_level='DEBUG')
update_config('tool_creator', log_level='DEBUG')
engine = IfcAnswerEngine(llm=llm)
```

### 2. Fast Prototyping
```python
update_config('tool_creator', max_iter=1)
update_config('tool_programmer', max_iters=5)
engine = IfcAnswerEngine(llm=llm)
```

### 3. Production Settings
```python
from src.config.agents import IfcAnswerEngineConfig

prod_config = IfcAnswerEngineConfig(
    log_level="ERROR",
    max_retry=1,
    max_iters=5
)
engine = IfcAnswerEngine(llm=llm, config=prod_config)
```

## Breaking Changes

### Removed Parameters
These parameters are now handled through config objects:

**IfcAnswerEngine:**
- `max_iters` → `config.max_iters`
- `max_retry` → `config.max_retry`
- `log_level` → `config.log_level`
- `max_tokens_logs` → `config.max_tokens_logs`
- `max_tokens_output` → `config.max_tokens_output`
- `import_all_created_tools` → `config.import_all_created_tools`
- `max_iter_tool_creator` → `config.tool_creator.max_iter`
- `max_iter_sub_agents_tool_creator` → removed (sub-agents use own configs)
- `add_code_prefix` → `config.add_code_prefix`

**Sub-Agents:**
All sub-agents now take a single `config` parameter instead of individual parameters.

## Backward Compatibility

The new system is **not** backward compatible by design. This breaking change was necessary to achieve the clean architecture goals. However, migration is straightforward with the examples above.

## Testing the Migration

Run the example file to verify everything works:
```bash
python examples/config_usage.py
```

This will demonstrate all the new configuration patterns and verify the system is working correctly. 