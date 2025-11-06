# Specs for updating the run_evaluation.py script

## Status quo
Currently, this script is:
- overbloated (790 lines)
- way too long
- uses OOP, without any clear benefit
- has complex CLI with 12+ arguments
- uses cumbersome engine factory pattern

## Goal
The goal is to move away from the current implementation (basically starts from scratch), and write a new script to run the evaluation process.
This new script should:
- avoid using classes, unless they provide a definitive and clear benefit
- start the evaluation run in mlflow in the "Evaluation" experiment, and created a nested run for each question processed
- make it possible to pass arguments when executing the script. Argument needed:
  - start (index of the starting sample in the devset)
  - nb_samples (nb of samples to process)
  all other arguments currently supported are not needed anymore

## Components
The new script should use the `cobbie_with_metrics` function from the `cobbie.py` instead of the current cumbersome engine implementation.

## Metrics
The metrics from `_calculate_and_log_metrics` should still be logged
The print statements were also decent and can be reused.

## Detailed Architecture Changes

### 1. **Simplified Architecture**
- **Remove OOP**: Eliminate `EvaluationRunner` class completely
- **Functional approach**: Use simple functions instead of complex state management
- **Direct integration**: Use `cobbie_with_metrics()` instead of engine factory pattern
- **Target length**: Under 200 lines (vs current 790 lines)

### 2. **Simplified CLI Arguments**
- **Remove**: Complex arguments like `--engine-type`, `--model`, `--provider`, `--load-compiled`, `--cache`, etc.
- **Keep only**: `--start` (index), `--nb_samples` (count), `--log-level`
- **Hardcode**: BAML engine with Z.AI GLM-4.6 configuration

### 3. **Components to Reuse (Largely Unchanged)**
- `_calculate_and_log_metrics()` - Move to module-level function
- `_print_results()` - Move to module-level function
- Answer verification with `verify_answer_with_metrics`
- MLflow nested run structure (main run + per-question runs)
- Progress tracking with tqdm

### 4. **New Implementation Structure**
```python
# ~30 lines: Imports and setup
# ~20 lines: Simple argument parsing
# ~15 lines: MLflow experiment setup
# ~40 lines: Main evaluation loop with cobbie_with_metrics
# ~50 lines: Reusable metrics calculation
# ~25 lines: Reusable print statements
# ~10 lines: main() function
# Total: ~190 lines
```

### 5. **Technical Integration**
- **Replace**: `engine.forward(question, ifc_path)`
- **With**: `cobbie_with_metrics(user_input=question, tools=tools_dict, model_path=ifc_path)`
- **Tools**: Direct import from `src.tools.initial`
- **No try/except**: Remove complex error handling as specified
- **Token tracking**: Leverage COBBIE's comprehensive collector metrics

### 6. **MLflow Integration**
- **Preserve**: Main run in "Evaluation" experiment
- **Preserve**: Nested runs for each question
- **Simplify**: Remove engine-specific parameter logging
- **Maintain**: Comprehensive metrics and token tracking

## Implementation Strategy
1. **Overwrite** the existing `scripts/run_evaluation.py` file completely (don't create duplicates)
2. Copy reusable functions (metrics, printing) from current implementation as module-level functions
3. Implement direct COBBIE integration replacing complex engine pattern
4. Setup MLflow experiment and nested runs
5. Add simplified argument parsing
6. Test with small sample size

## other
setup tracking uri and experiment name with mlflow
no try/except blocks
total length of the new script should be under 200 lines of code.
