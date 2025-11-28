# Tool Tracking for Evaluation Phase

## Overview

This specification describes the implementation of tool usage metrics tracking during the evaluation phase, mirroring the existing tool tracking system used in the training phase.

## Motivation

Currently, tool usage metrics are only tracked during training (`tool_usage_stats` table). To understand tool performance during evaluation and compare training vs. evaluation behavior, we need equivalent tracking for the evaluation phase.

## Design Principles

1. **Consistency**: Mirror the training phase structure as closely as possible
2. **Separation**: Keep evaluation metrics separate from training metrics
3. **Simplicity**: Use the same fields and tracking logic as training
4. **Continuity**: Support accumulating metrics across multiple evaluation runs

## Database Schema

### New Table: `tool_usage_stats_eval`

```sql
CREATE TABLE IF NOT EXISTS tool_usage_stats_eval (
    tool_name TEXT PRIMARY KEY NOT NULL,
    questions_when_included INTEGER DEFAULT 0 NOT NULL,
    questions_when_called INTEGER DEFAULT 0 NOT NULL,
    questions_correct_contribution INTEGER DEFAULT 0 NOT NULL,
    questions_wrong_contribution INTEGER DEFAULT 0 NOT NULL
);
```

### Field Descriptions

- `tool_name`: Primary key, name of the tool (without .py extension)
- `questions_when_included`: Counter for how many evaluation questions had this tool available
- `questions_when_called`: Counter for how many times the tool was actually invoked
- `questions_correct_contribution`: Counter for correct answers when this tool was used
- `questions_wrong_contribution`: Counter for wrong answers when this tool was used

### Differences from Training Table

The evaluation table omits `created_at_question` since tools are not created during evaluation, only used.

## Query Functions

Add to `src/db/query.py`:

### 1. `increment_eval_tool_inclusion(tool_names: List[str]) -> None`

Increments the inclusion counter for all tools available in the current evaluation question.

**Behavior**:
- Creates new entry if tool doesn't exist
- Increments `questions_when_included` by 1 for each tool
- Called once per question with the list of all available tools

### 2. `update_eval_tool_usage(tool_names: List[str], is_correct: bool) -> None`

Updates usage statistics for tools that were actually called.

**Behavior**:
- Increments `questions_when_called` by 1
- Increments `questions_correct_contribution` if `is_correct=True`
- Increments `questions_wrong_contribution` if `is_correct=False`
- Only processes tools that exist in the table

### 3. `get_all_eval_tool_stats() -> List[ToolUsageStatsEval]`

Retrieves all evaluation tool statistics, ordered by tool name.

**Returns**: List of `ToolUsageStatsEval` objects

### 4. `clear_eval_tool_stats() -> int`

Clears all evaluation tool statistics.

**Returns**: Number of rows deleted
**Use case**: Fresh start with `--reset-tool-metrics` flag

## CLI Arguments

Add to `scripts/run_evaluation.py`:

### `--track-tools {true|false}`

- **Type**: Boolean (via lambda parser)
- **Default**: `true`
- **Description**: Enable/disable tool usage tracking
- **Example**: `--track-tools false`

### `--reset-tool-metrics`

- **Type**: Flag (action='store_true')
- **Default**: `false`
- **Description**: Clear all evaluation tool metrics before starting
- **Example**: `--reset-tool-metrics`

## Integration Points

### A. Imports (Top of file)

```python
from src.util.extract_tool_usage import extract_tools_used
from src.db.query import (
    increment_eval_tool_inclusion,
    update_eval_tool_usage,
    get_all_eval_tool_stats,
    clear_eval_tool_stats,
)
```

### B. Handle Reset Flag (In `main()`, after args parsing)

```python
# Handle tool metrics reset
if args.reset_tool_metrics:
    deleted_count = clear_eval_tool_stats()
    logger.info(f"Cleared {deleted_count} evaluation tool metric entries")
```

### C. Track Per Question (In `process_question()`)

**Location**: After answer verification (after line ~336)

**Requirements**:
- `process_question()` needs access to `args` parameter
- Need to capture and pass the execution history from cobbie

```python
# Track tool usage (after answer verification)
if args.track_tools:
    # Track tools that were available for this question
    available_tools = list(tools_dict.keys())
    increment_eval_tool_inclusion(available_tools)

    # Track tools that were actually used
    tools_used = extract_tools_used(history)
    is_correct = classification == "correct"
    update_eval_tool_usage(tools_used, is_correct)

    # Log to MLflow
    mlflow.log_metric("num_tools_used", len(tools_used))
    logger.info(f"Tracked usage of {len(tools_used)} tools: {tools_used}")
```

### D. Print Summary Report (New function before `main()`)

```python
def print_tool_metrics_summary():
    """Print summary of tool usage metrics from evaluation."""
    eval_stats = get_all_eval_tool_stats()

    if not eval_stats:
        print("\nNo tool usage metrics available.")
        return

    print("\n" + "=" * 80)
    print("TOOL USAGE METRICS (EVALUATION)")
    print("=" * 80)

    # Sort by usage frequency
    sorted_stats = sorted(
        eval_stats,
        key=lambda s: s.questions_when_called or 0,
        reverse=True
    )

    print(f"\n{'Tool Name':<30} {'Included':<10} {'Called':<10} {'Correct':<10} {'Wrong':<10} {'Call Rate':<10}")
    print("-" * 80)

    for stat in sorted_stats:
        included = stat.questions_when_included or 0
        called = stat.questions_when_called or 0
        correct = stat.questions_correct_contribution or 0
        wrong = stat.questions_wrong_contribution or 0
        call_rate = (called / included * 100) if included > 0 else 0

        print(f"{stat.tool_name:<30} {included:<10} {called:<10} {correct:<10} {wrong:<10} {call_rate:<9.1f}%")

    # Summary statistics
    total_included = sum(s.questions_when_included or 0 for s in eval_stats)
    total_called = sum(s.questions_when_called or 0 for s in eval_stats)
    total_correct = sum(s.questions_correct_contribution or 0 for s in eval_stats)
    total_wrong = sum(s.questions_wrong_contribution or 0 for s in eval_stats)

    print("\n" + "-" * 80)
    print(f"{'TOTAL':<30} {total_included:<10} {total_called:<10} {total_correct:<10} {total_wrong:<10}")
    print("=" * 80)
```

### E. Call Summary (In `main()`, after results)

```python
# Print tool metrics summary
if args.track_tools:
    print_tool_metrics_summary()
```

## Implementation Steps

### Step 1: Create Database Table - DONE

### Step 2: Regenerate Models - DONE

```bash
sqlacodegen sqlite:///src/db/db.db --generator sqlmodels --outfile src/db/models.py
```

This will add the `ToolUsageStatsEval` model automatically.

### Step 3: Add Query Functions

Edit `src/db/query.py` and add:
1. Import the new model: `from src.db.models import ToolUsageStatsEval`
2. Implement the 4 query functions described above

### Step 4: Modify Evaluation Script

Edit `scripts/run_evaluation.py`:
1. Add imports
2. Add CLI arguments to parser
3. Add reset flag handler in `main()`
4. Modify `process_question()` signature to accept `args`
5. Add tracking calls in `process_question()`
6. Add `print_tool_metrics_summary()` function
7. Call summary function at end of `main()`

### Step 5: Test

```bash
# Test with tracking enabled (default)
uv run scripts/run_evaluation.py --start 0 --nb-samples 5

# Test with tracking disabled
uv run scripts/run_evaluation.py --start 0 --nb-samples 5 --track-tools false

# Test with reset
uv run scripts/run_evaluation.py --start 0 --nb-samples 5 --reset-tool-metrics

# Test continuation (should accumulate)
uv run scripts/run_evaluation.py --start 5 --nb-samples 5
```

## Usage Examples

### Normal Evaluation (with tracking)

```bash
uv run scripts/run_evaluation.py --start 0 --nb-samples 10
```

Metrics accumulate across runs.

### Fresh Start

```bash
uv run scripts/run_evaluation.py --start 0 --nb-samples 50 --reset-tool-metrics
```

Clears all previous evaluation metrics before starting.

### Disable Tracking

```bash
uv run scripts/run_evaluation.py --start 0 --nb-samples 10 --track-tools false
```

### Continue Evaluation (Accumulate Metrics)

```bash
# First batch
uv run scripts/run_evaluation.py --start 0 --nb-samples 25

# Second batch (metrics accumulate)
uv run scripts/run_evaluation.py --start 25 --nb-samples 25
```

## Expected Output

At the end of each evaluation run with tracking enabled:

```
================================================================================
TOOL USAGE METRICS (EVALUATION)
================================================================================

Tool Name                      Included   Called     Correct    Wrong      Call Rate
--------------------------------------------------------------------------------
get_wall_properties            50         35         30         5          70.0%
calculate_total_area           50         28         25         3          56.0%
extract_door_info              50         15         12         3          30.0%
list_space_names               50         8          7          1          16.0%
...

--------------------------------------------------------------------------------
TOTAL                          200        86         74         12
================================================================================
```

## Benefits

1. **Performance Analysis**: Understand which tools are most/least useful during evaluation
2. **Training Comparison**: Compare tool usage patterns between training and evaluation
3. **Tool Validation**: Identify tools that work well in training but fail in evaluation
4. **Debugging**: Track which tools contribute to wrong answers
5. **Optimization**: Identify unused tools that could be removed
