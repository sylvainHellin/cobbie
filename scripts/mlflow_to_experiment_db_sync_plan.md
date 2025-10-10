# MLflow to Experiment Database Sync Script Plan

## Overview

This document outlines a comprehensive plan for creating a script to synchronize MLflow experiments, runs, traces, and spans to the experiment database. The script will focus on the "Evaluation" and "Training" experiments only, with the ability to configure additional experiments later.

## Key Requirements & Constraints

1. **Target Experiments**: Only sync "Training" and "Evaluation" experiments (configurable)
2. **Deduplication**: Use MLflow IDs directly as primary keys in the experiment database
3. **Full Sync**: Perform complete sync each time, skipping already existing IDs
4. **Error Handling**: Break on errors to allow fixing before proceeding
5. **Performance**: Efficient processing of potentially tens of thousands of traces

## Database Schema Mapping

### MLflow Database Structure
- `experiments` (experiment_id, name, creation_time, lifecycle_stage, etc.)
- `runs` (run_uuid, name, start_time, end_time, status, experiment_id, etc.)
- `trace_info` (request_id, experiment_id, timestamp_ms, status, execution_time_ms)
- `trace_request_metadata` (request_id, key, value) - contains trace inputs/outputs/tags
- Supporting tables: metrics, params, tags

### Experiment Database Structure
- `experiment` (id, name) - uses MLflow experiment_id as id
- `run` (id, experiment_id, name, cost, duration, tokens, etc.) - uses MLflow run_uuid as id
- `trace` (id, run_id, question_id, answer, status, tools, etc.) - uses MLflow request_id as id
- `span` (id, trace_id, timing data, tokens, cost, llm, input/output data) - needs span ID from MLflow API
- Supporting tables: dataset, ifcmodels

## Critical Technical Discovery

**Span Data Access**: Spans are NOT stored as database tables in MLflow SQLite. They must be accessed programmatically through MLflow's Python API:
```python
# From src/engine/util/query_mlflow.py:114-122
traces = client.search_traces(experiment_ids=[exp_id], run_id=run_id)
for trace in traces:
    spans = trace.data.spans  # This is the only way to access spans
```

## Data Flow and Relationships

```
MLflow Database → MLflow Python API → Experiment Database

Experiments:
experiments.experiment_id → experiment.id

Runs:
runs.run_uuid → run.id
runs.experiment_id → run.experiment_id (foreign key)

Traces:
trace_info.request_id → trace.id
trace_info.experiment_id → trace.run_id (via runs table)

Spans:
trace.data.spans (via API) → span.id
span.trace_id → span.trace_id (foreign key to trace.id)
```

## Implementation Plan

### Phase 1: Script Foundation

**File**: `scripts/sync_mlflow_to_experiment_db.py`

**Dependencies**:
```python
from sqlmodel import Session, select
import mlflow
from mlflow import MlflowClient
from src.experiment.db import EXPERIMENT_DB_ENGINE, MLFLOW_DB_ENGINE
from src.experiment.db.experiment_models import Experiment, Run, Trace, Span
from src.experiment.db.mlflow_models import Experiments, Runs, TraceInfo
from src.engine.util.query_mlflow import CustomMLFlowClient
```

**Configuration**:
```python
TARGET_EXPERIMENTS = ["Training", "Evaluation"]  # Make configurable
MLFLOW_TRACKING_URI = "http://127.0.0.1:5000"
SKIP_EXISTING_RUNS = True  # CLI argument support
```

### Phase 2: Experiment Sync

**Approach**: Reuse existing `import_mlflow_experiments()` from `src/experiment/db/query.py:67-94`

**Implementation**:
- Already properly handles experiment synchronization
- Uses `str(res.experiment_id)` as primary key
- Filters by `TARGET_EXPERIMENTS` configuration
- Prevents duplicates by checking existing IDs

### Phase 3: Run Sync Enhancement

**Approach**: Enhance existing `import_mlflow_runs()` from `src/experiment/db/query.py:96-166`

**Key Mappings**:
- `runs.run_uuid` → `run.id` (primary key)
- `runs.experiment_id` → `run.experiment_id` (convert to string)
- `runs.name` → `run.name`
- `runs.start_time` → `run.timestamp` (convert from ms to datetime)
- `runs.end_time - runs.start_time` → `run.duration`
- Extract cost/tokens from metrics table
- Generate MLflow URL: `http://127.0.0.1:5000/#/experiments/{exp_id}/runs/{run_uuid}`

**Filtering**: Only process runs from target experiments

### Phase 4: Trace Sync (New Implementation)

**Function**: `import_mlflow_traces()`

**Process**:
1. Query existing trace IDs from experiment database
2. Query MLflow `trace_info` table for traces from target experiments
3. For each trace not in experiment database:
   - Extract basic info from `trace_info` table
   - Get trace metadata from `trace_request_metadata` table
   - Parse `mlflow.traceInputs` and `mlflow.traceOutputs` JSON
   - Extract similarity scores and metrics from trace tags

**Key Data Extraction**:
```python
# From trace_info table
trace.request_id → trace.id
trace.execution_time_ms → trace.duration
trace.status → trace.status (OK/ERROR)

# From trace_request_metadata table
mlflow.traceOutputs → trace.answer (JSON parsing)
similarity_score → trace.accuracy (from tags)
tool created/merged/updated → trace.tools (from tags)

# Run relationship
Find run_id via experiment_id mapping
```

### Phase 5: Span Sync (Most Complex)

**Function**: `import_mlflow_spans()`

**Process**:
1. Use MLflow Python API to get traces with spans
2. For each trace in experiment database:
   - Use `CustomMLFlowClient.search_traces()` with experiment_id and run_id
   - Access `trace.data.spans` for span data
   - Process each span and insert into experiment database
   - Update trace `nb_spans` count

**Key Data Mappings**:
```python
# Span identification
span.request_id + span.name → span.id (generate composite ID)
span.trace_id → span.trace_id (foreign key)

# Timing data
span.start_time_ms → span.start_time
span.end_time_ms → span.end_time
span.end_time_ms - span.start_time_ms → span.duration

# Type and attributes
span.attributes["mlflow.spanType"] → span.type
span.attributes.get("model") → span.llm

# Token and cost data
span.attributes["mlflow.spanInputs"] → span.input_data (JSON)
span.attributes["mlflow.spanOutputs"] → span.output_data (JSON)

# Extract metrics from span data
input_tokens/output_tokens/cost from span metrics
```

### Phase 6: Tool Classification Logic

**Training Pipeline Tool Detection** (from `src/experiment/training/training_pipeline.py:84-94`):

```python
# Extract from MLflow trace tags
tools = "none"
if "tool merged" in trace_tags:
    tools = "updated"  # Note: pipeline uses "merged" tag but sets "updated"
elif "tool created" in trace_tags:
    tools = "created"
elif "tools merged" in trace_tags:
    tools = "merged"

# Validation: Must match enum values in trace.tools
ALLOWED_TOOLS = ['created', 'merged', 'updated', 'deleted', 'none']
```

**Evaluation Pipeline**: Always use `tools = "none"` (no tool creation/merging in evaluation)

### Phase 7: Question ID Mapping

**Challenge**: Connecting traces to questions (`trace.question_id`)

**Solution**:
1. **Training runs**: Use the question ID from training dataset (parse from trace name or metadata)
2. **Evaluation runs**: Map evaluation questions to traces (may need additional logic)

**Training Pipeline Pattern** (from `training_pipeline.py:71-73`):
```python
# Trace name pattern: "train_question_id_{qa_pair.id}"
trace_name = f"train_question_id_{qa_pair.id}"
# Extract question_id from trace name or metadata
```

### Phase 8: Orchestration and CLI

**Main Function**: `sync_mlflow_to_experiment_db()`

**CLI Arguments**:
```python
import argparse

parser = argparse.ArgumentParser(description='Sync MLflow data to experiment database')
parser.add_argument('--experiments', nargs='+', default=['Training', 'Evaluation'],
                    help='Experiments to sync (default: Training Evaluation)')
parser.add_argument('--skip-existing-runs', action='store_true',
                    help='Skip runs that already exist in experiment database')
parser.add_argument('--dry-run', action='store_true',
                    help='Preview what would be imported without making changes')
parser.add_argument('--verbose', '-v', action='store_true',
                    help='Enable verbose logging')
```

**Processing Flow**:
```python
def main():
    # 1. Setup MLflow client and database connections
    # 2. Sync experiments (reuse existing function)
    # 3. Sync runs (enhanced existing function, optional skip-existing)
    # 4. Sync traces (new implementation)
    # 5. Sync spans (new implementation via MLflow API)
    # 6. Report summary statistics
```

### Phase 9: Performance Optimization

**Strategies**:
1. **Batch Processing**: Process in chunks to manage memory
2. **Selective Processing**: Skip existing runs/traces based on CLI args
3. **Database Transactions**: Use transactions for data integrity
4. **Progress Reporting**: Log progress for large datasets
5. **Early Termination**: Stop on first error as requested

**Query Optimization**:
```python
# Get existing IDs in batches for efficient deduplication
existing_trace_ids = {trace.id for trace in session.exec(select(Trace).limit(10000))}
existing_run_ids = {run.id for run in session.exec(select(Run).limit(1000))}
```

## Data Validation Rules

### Trace Validation
- `trace.status` must be "OK" or "ERROR"
- `trace.tools` must be one of: 'created', 'merged', 'updated', 'deleted', 'none'
- `trace.accuracy` must be between 0 and 1 if present
- `trace.question_id` must reference existing dataset entry
- `trace.run_id` must reference existing run

### Span Validation
- `span.trace_id` must reference existing trace
- Token counts must be non-negative integers
- Costs must be non-negative floats
- Timestamps must be valid datetime values

## Error Handling Strategy

**Principles**:
1. **Fail Fast**: Stop processing on first error
2. **Detailed Logging**: Log context for debugging
3. **Transaction Safety**: Use database transactions
4. **Data Validation**: Validate before insertion

**Error Types to Handle**:
- Database connection failures
- MLflow API errors
- Data format/parsing errors
- Foreign key constraint violations
- Data type conversion errors

## Testing Strategy

**Test Cases**:
1. **Empty Database**: Initial sync from scratch
2. **Partial Sync**: Sync with existing data (deduplication)
3. **Large Dataset**: Performance testing with many traces
4. **Error Recovery**: Handling of malformed data
5. **Tool Classification**: Correct tool detection logic

**Validation Points**:
- Count consistency between MLflow and experiment DB
- Data integrity of relationships (foreign keys)
- Correct tool classification for training runs
- Accurate span data extraction from MLflow API

## Configuration Requirements

**Future Configurability**:
```python
# Config file support (YAML/JSON)
{
    "target_experiments": ["Training", "Evaluation"],
    "mlflow_tracking_uri": "http://127.0.0.1:5000",
    "batch_size": 1000,
    "skip_existing_runs": true,
    "enable_span_sync": true,
    "tool_classification_rules": {
        "training_pipeline": true,
        "evaluation_pipeline": false
    }
}
```

## Summary of Script Flow

```
1. Parse CLI arguments and setup configuration
2. Initialize MLflow client and database connections
3. Sync experiments (reuse existing function)
   - Filter by target experiments
   - Use MLflow experiment_id as primary key
4. Sync runs (enhanced existing function)
   - Skip existing runs if requested
   - Use MLflow run_uuid as primary key
   - Extract metrics and calculate duration/cost
5. Sync traces (new implementation)
   - Query trace_info for target experiments
   - Parse trace metadata for answers and metrics
   - Apply tool classification logic
   - Map to question_id (training: from dataset, evaluation: TBD)
6. Sync spans (new implementation via MLflow API)
   - Use CustomMLFlowClient to access trace.data.spans
   - Extract span attributes and metrics
   - Update trace span counts
7. Commit transactions and report statistics
```

## Next Steps

This plan provides a comprehensive roadmap for implementing the MLflow to experiment database sync script. The key challenges are:

1. **Span Data Access**: Requires MLflow Python API, not direct database access
2. **Question Mapping**: Need logic to connect traces to questions, especially for evaluation runs
3. **Tool Classification**: Implement logic based on training pipeline logging patterns
4. **Performance**: Efficient processing of potentially large datasets

The implementation should proceed phase by phase, with thorough testing at each stage to ensure data integrity and correctness.