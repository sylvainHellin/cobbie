# Unified Evaluation Script - Clean Implementation Plan

## Overview
Create a single unified evaluation script that eliminates `EvaluationPipeline` and uses the engines directly via `create_engine()` factory. Both DSPy and BAML engines will use the same clean evaluation approach.

## Key Insights

### Eliminate EvaluationPipeline
The current `EvaluationPipeline` is just unnecessary wrapper code that:
- Creates an engine via `create_engine()` (which we can do directly)
- Iterates through dataset (simple loop)
- Calls engine + AnswerVerifier (direct calls)
- Collects metrics (can be done directly)

### Unified Processing Model
Both engines will use the **same simple approach**:
1. Create engine via `create_engine(engine_type)`
2. Loop through dataset manually
3. Extract IFC path from `question_data.ifc.model_path` (per question)
4. Call `engine.forward(question, ifc_path)`
5. Run `AnswerVerifier` for similarity scoring
6. Collect metrics manually
7. Use BAML-style comprehensive MLflow logging for both

## Implementation Steps

### 1. Create New Unified `scripts/run_evaluation.py`
Replace both existing scripts with a clean implementation that:

### 2. Core Parameters (CLI)
```bash
# Engine selection
--engine-type {dspy,baml,auto}     # Engine type (default: auto from config)

# Core parameters
--model <name>                     # Override model name
--provider <name>                  # Override provider name
--num-samples <int>                # Number of samples (default: 10)
--experiment-name <string>         # MLflow experiment name
--log-level <level>                # Logging level

# DSPy-specific flags
--load-compiled                    # Load compiled model (DSPy only)
--cache                            # Enable DSPy cache (DSPy only)

# Existing functionality
--run-id <id>                      # Continue existing MLflow run
```

### 3. Clean Unified Implementation
```python
class UnifiedEvaluationRunner:
    def __init__(self, engine_type, model, provider, num_samples, load_compiled, cache, ...):
        # Determine engine type (auto/from param)
        # Create LLM config with overrides
        # Create engine via create_engine(engine_type=..., config=...)
        # Setup MLflow

    def run_evaluation(self):
        # Create main MLflow run
        # Loop through dataset manually
        for question_data in dataset:
            # Create nested MLflow run per question
            # Extract IFC path: question_data.ifc.model_path
            # Call engine.forward(question, ifc_path)
            # Run AnswerVerifier for similarity
            # Collect all metrics (engine + verification)
            # Log comprehensively to MLflow

        # Calculate final metrics
        # Log to main MLflow run
        # Print unified results
```

### 4. Unified Metrics Collection
**Core Metrics (both engines)**:
- Success rate, similarity scores, execution time
- Token usage (if available from engine)
- Answer quality metrics

**Engine-Specific Metrics**:
- DSPy: Cache hits/misses, compilation info
- BAML: Iterations, BAML calls, code executions

### 5. Unified MLflow Logging
Use BAML-style manual logging for **both engines**:
- **Main Run**: Overall evaluation metrics
- **Nested Runs**: Individual question processing
- **Comprehensive Spans**: Engine operations, AnswerVerifier
- **Engine-Specific Attributes**: Type, specific metrics

### 6. Configuration Handling
```python
# Base config from AGENT_CONFIGS.ifc_answer_engine
config = AGENT_CONFIGS.ifc_answer_engine

# Apply CLI overrides
if model: config.llm.model_name = model
if provider: config.llm.provider_name = provider

# Set engine type
if engine_type != "auto":
    config.engine_type = engine_type

# Create engine
engine = create_engine(config=config)

# Apply DSPy-specific settings
if config.engine_type == "dspy":
    dspy.configure_cache(enable_disk_cache=cache)
    if load_compiled and hasattr(engine, 'load'):
        engine.load(path=compiled_path)
```

### 7. Migration Strategy
- **Backup**: Move old scripts to `scripts/backup/`
- **Replace**: Create new unified `scripts/run_evaluation.py`
- **Remove**: Delete `src/experiment/evaluation/evaluation.py` (EvaluationPipeline no longer needed)
- **Update**: Any references to EvaluationPipeline in other code
- **Test**: Validate both engines work identically

## Key Benefits
- **Single Script**: One evaluation approach for both engines
- **Clean Architecture**: Direct engine usage, no unnecessary wrappers
- **Unified Metrics**: Same comprehensive metrics collection
- **Simple Interface**: Minimal CLI parameters with smart defaults
- **Correct IFC Handling**: Per-question IFC paths from dataset
- **Future-Proof**: Easy to add new engines

## Implementation Details

### IFC Path Handling
- Remove hardcoded `--ifc-model-path` parameter completely
- Extract IFC path per question: `question_data.ifc.model_path`
- Ensure each question uses its correct associated IFC model

### DSPy Specific Features
- `--load-compiled`: Load optimized module if available
- `--cache`: Enable DSPy disk cache
- Only applied when engine_type is "dspy"

### BAML Specific Features
- Automatically collect BAML metrics (iterations, calls)
- No additional parameters needed
- Use engine's default max_iterations from config

### AnswerVerifier Integration
- Use same AnswerVerifier for both engines
- Run verification after each question processing
- Collect similarity scores consistently

### Error Handling
- Unified error handling for both engine types
- Proper MLflow logging of failures
- Graceful degradation when engines fail

## Files to be Modified/Created
- **NEW**: `scripts/run_evaluation.py` (unified script)
- **BACKUP**: `scripts/backup/run_evaluation_dspy_original.py`
- **BACKUP**: `scripts/backup/run_baml_evaluation_original.py`
- **REMOVE**: `src/experiment/evaluation/evaluation.py` (if no references exist)
- **UPDATE**: Any documentation referencing old scripts

## Testing Strategy
- Test with both engine types on small dataset
- Verify MLflow logging works correctly
- Confirm metrics collection is consistent
- Validate IFC path handling per question
- Test DSPy-specific features (cache, compiled models)
- Test BAML-specific metrics collection