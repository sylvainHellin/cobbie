# MLflow to Experiment Database Sync Script

This script synchronizes experiments, runs, traces, and spans from MLflow to the experiment database.

## Overview

The `sync_mlflow_to_experiment_db.py` script provides a comprehensive solution for transferring MLflow tracking data to the experiment database. It handles:

- **Experiments**: Syncs target experiments (Training, Evaluation by default)
- **Runs**: Imports run metadata, metrics, and timing information
- **Traces**: Extracts trace data from MLflow trace_info table
- **Spans**: Accesses span data via MLflow Python API

## Features

- **Deduplication**: Uses MLflow IDs as primary keys to prevent duplicates
- **Configurable**: Target experiments can be specified via command line
- **Performance Optimized**: Batch processing and selective sync options
- **Error Handling**: Comprehensive error reporting and transaction safety
- **Tool Classification**: Extracts tool usage patterns from training pipeline logs
- **Dry Run Mode**: Preview what would be synced without making changes

## Usage

### Basic Usage

```bash
# Sync all data for default experiments (Training, Evaluation)
uv run python scripts/sync_mlflow_to_experiment_db.py

# Dry run to preview what would be synced
uv run python scripts/sync_mlflow_to_experiment_db.py --dry-run

# Verbose output
uv run python scripts/sync_mlflow_to_experiment_db.py --verbose
```

### Advanced Options

```bash
# Sync specific experiments
uv run python scripts/sync_mlflow_to_experiment_db.py --experiments Training Evaluation

# Skip existing runs (faster for subsequent syncs)
uv run python scripts/sync_mlflow_to_experiment_db.py --skip-existing-runs

# Combine options
uv run python scripts/sync_mlflow_to_experiment_db.py \
  --experiments Training Evaluation \
  --skip-existing-runs \
  --verbose \
  --dry-run
```

## Command Line Options

| Option | Description |
|--------|-------------|
| `--experiments` | List of experiment names to sync (default: Training Evaluation) |
| `--skip-existing-runs` | Skip runs that already exist in experiment database |
| `--dry-run` | Preview what would be imported without making changes |
| `--verbose, -v` | Enable verbose logging |

## Data Mapping

### Experiments
- **Source**: `mlflow.experiments` table
- **Target**: `experiment` table
- **Key**: `experiments.experiment_id` → `experiment.id`

### Runs
- **Source**: `mlflow.runs` table + metrics
- **Target**: `run` table
- **Key**: `runs.run_uuid` → `run.id`
- **Fields**: name, duration, cost, tokens, accuracy, timestamp, URL

### Traces
- **Source**: `mlflow.trace_info` + `trace_request_metadata` + `trace_tags`
- **Target**: `trace` table
- **Key**: `trace_info.request_id` → `trace.id`
- **Fields**: answer, status, tools, accuracy, duration, metadata

### Spans
- **Source**: MLflow Python API (`trace.data.spans`)
- **Target**: `span` table
- **Key**: Generated composite ID
- **Fields**: timing, type, LLM, input/output data, tokens, cost

## Tool Classification Logic

The script extracts tool usage from training pipeline trace tags:

- `"tool merged"` → `tools = "updated"`
- `"tool created"` → `tools = "created"`
- `"tools merged"` → `tools = "merged"`
- Default → `tools = "none"`

## Error Handling

- **Fail Fast**: Script stops on first error for debugging
- **Transaction Safety**: Database transactions ensure data integrity
- **Detailed Logging**: Comprehensive error messages and progress tracking
- **Statistics Summary**: Reports sync results and any errors encountered

## Performance Considerations

- **Selective Processing**: Only processes target experiments
- **Batch Operations**: Efficient database operations
- **Memory Management**: Processes large datasets in manageable chunks
- **Existing Data Skip**: Option to skip already processed runs

## Dependencies

- `sqlmodel`: Database ORM and session management
- `mlflow`: MLflow Python API for span access
- `src.experiment.db`: Local database models and engines
- `src.engine.util.query_mlflow`: Custom MLflow client

## Examples

### Initial Full Sync
```bash
# First time sync - dry run first
uv run python scripts/sync_mlflow_to_experiment_db.py --dry-run --verbose

# Then actual sync
uv run python scripts/sync_mlflow_to_experiment_db.py --verbose
```

### Incremental Sync
```bash
# Sync new data only, skipping existing runs
uv run python scripts/sync_mlflow_to_experiment_db.py --skip-existing-runs --verbose
```

### Custom Experiments
```bash
# Sync specific experiments
uv run python scripts/sync_mlflow_to_experiment_db.py --experiments "Custom Experiment" --verbose
```

## Troubleshooting

### Common Issues

1. **No experiments found**: Verify experiment names match exactly in MLflow
2. **Trace-to-run mapping failures**: Check that runs exist for target experiments
3. **Span sync failures**: Ensure MLflow server is running and accessible
4. **Database connection errors**: Verify database configuration and permissions

### Debug Mode

Use `--dry-run --verbose` to debug issues without making changes:

```bash
uv run python scripts/sync_mlflow_to_experiment_db.py --dry-run --verbose
```

## Technical Notes

- Spans cannot be accessed directly from MLflow database tables
- MLflow Python API is required for span data extraction
- Tool classification logic matches training pipeline logging patterns
- Question ID mapping relies on training dataset patterns
- All MLflow IDs are preserved as primary keys for traceability

## Related Files

- `scripts/mlflow_to_experiment_db_sync_plan.md`: Comprehensive implementation plan
- `src/experiment/db/query.py`: Original import functions (reused/enhanced)
- `src/engine/util/query_mlflow.py`: Custom MLflow client for span access
- `src/experiment/training/training_pipeline.py`: Tool classification logic reference