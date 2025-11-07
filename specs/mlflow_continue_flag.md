# MLflow Continue Flag Implementation Plan

## Overview
Implement a `--continue` flag for the training script that allows resuming MLflow runs in the "Training" experiment, enabling batch processing that combines into a single run to mitigate memory leak issues.

## Problem Statement
The current training script suffers from MLflow memory leaks (unclean semaphore objects) that cause it to crash when running for extended periods. The proposed solution allows running smaller batches that log to the same MLflow run.

## Implementation Details

### 1. New Command Line Arguments
- Add `--continue [run_id]` flag with optional run_id parameter
- If run_id provided: use that specific run
- If no run_id provided: find most recent run in "Training" experiment
- Keep existing `--start` and `--end` arguments for batch control
- Add validation to prevent conflicting usage

### 2. New Utility File: `/src/utils/mlflow_utils.py`
Create utility functions:
- `get_most_recent_training_run()` - Find most recent run in "Training" experiment
- `get_run_by_id(run_id)` - Get specific run by ID with validation
- Error handling for edge cases (no runs, invalid run_id, etc.)

### 3. Main Function Modifications
Refactor MLflow run initialization in `scripts/run_training_phase.py`:

```python
# Determine run_id based on --continue flag
if args.continue:
    if args.continue is True:  # --continue flag without run_id
        run_id = get_most_recent_training_run()
    else:  # --continue <run_id>
        run_id = get_run_by_id(args.continue)
else:
    run_id = None  # Will create new run

# Always use mlflow.start_run(run_id=run_id)
with mlflow.start_run(run_id=run_id) as run:
    # Existing training logic
```

### 4. Argument Parser Changes
```python
parser.add_argument("--continue", dest="continue_run", nargs="?", const=True,
                   help="Continue most recent run or specific run ID")
```

### 5. Usage Examples
```bash
# First batch: create new run
uv run scripts/run_training_phase.py --start 0 --end 10

# Continue most recent run
uv run scripts/run_training_phase.py --continue --start 10 --end 20

# Continue specific run
uv run scripts/run_training_phase.py --continue e990e99c62434fa290bed615af72b81f --start 20 --end 30
```

### 6. Key Implementation Points
- Clean separation of concerns with utility file
- Unified run initialization with `mlflow.start_run(run_id=run_id)`
- Proper argument parsing for optional run_id parameter
- Comprehensive error handling and validation
- Preserve all existing MLflow logging structure
- Handle nested runs properly within resumed context

### 7. Error Handling
- No existing runs: clear error message suggesting creating new run
- Invalid run_id: clear error message with valid run ID format
- Run already finished: allow continuation for batch processing
- Corrupted state: graceful fallback to new run creation

### 8. Benefits for Memory Leak Issue
- Run smaller batches (e.g., 10 QA pairs at a time)
- Each batch logs to the same MLflow run
- If script crashes due to memory leak, next batch continues the same run
- No need to modify the core training logic
- Maintains experiment tracking continuity

## Files to Modify
1. `scripts/run_training_phase.py` - Add continue flag and run initialization logic
2. `src/utils/mlflow_utils.py` - New utility file for MLflow operations

## Testing Strategy
- Test continuation with and without specific run ID
- Test error handling for invalid scenarios
- Verify that MLflow logging works correctly across batch continuations
- Test that tool state persists correctly across continued runs