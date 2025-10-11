# Training Batch Processing and Resume Plan

## Overview

This document outlines a comprehensive plan to add batch processing and resume functionality to the IFC Answer Engine training script. The implementation addresses memory leaks in DSPy by using process isolation and MLflow-based state management.

## Problem Statement

- **Memory Leaks**: DSPy library has underlying memory leaks related to semaphore objects
- **Long Training Runs**: Large training sets cause memory accumulation over time
- **Need for Resume Capability**: Training runs should be resumable after failures
- **MLflow Integration**: All training progress must be tracked in MLflow

## Solution Architecture

### Core Design Principles

1. **Process Isolation**: Each batch runs in a separate Python process
2. **MLflow-Only State**: Resume state stored only in MLflow traces (no local persistence)
3. **Training-Only Focus**: Remove optimizer and evaluation steps from training script
4. **Fixed Batch Size**: 30 questions per batch
5. **Robust Error Handling**: Failed batches trigger process restart and retry

### Architecture Components

#### 1. Batch Worker Script (`scripts/run_training_batch.py`)
- Standalone script that processes exactly one batch of QA pairs
- Full dependency reloading for each process
- MLflow connection validation (fails if server unavailable)
- Comprehensive logging to both console and MLflow

#### 2. Main Training Script (`scripts/run_training.py`)
- Orchestrates batch processing
- Handles resume logic via MLflow traces
- Manages process lifecycle and retries
- Provides consolidated metrics reporting

#### 3. MLflow Integration
- All state tracking via MLflow traces
- Question IDs logged in span names: `train_question_id_{id}`
- Batch-level metrics logged after each batch
- Resume logic based on trace analysis

## Implementation Plan

### Phase 1: Batch Worker Script

#### 1.1 Script Structure
```python
#!/usr/bin/env python3
# scripts/run_training_batch.py
"""
Single batch processor for IFC training.
Processes exactly one batch of QA pairs with full dependency reloading.
"""

import argparse
import sys
import time
from datetime import datetime
from typing import List

# Full imports - each process starts fresh
import dspy
import mlflow
import mlflow.dspy
from tqdm import tqdm

from src.config.agents import TrainingPipelineConfig
from src.config.llm import LLM
from src.engine import TrainingModule
from src.engine.schemas import OutputsCollection, QA_Pair
from src.engine.util import get_logger
from src.experiment.datasets import load_train_dev_split
```

#### 1.2 Core Processing Function
```python
def process_single_batch(batch: List[QA_Pair], config) -> OutputsCollection:
    """Process a single batch of QA pairs with full MLflow tracking."""

    # Setup fresh MLflow context
    with mlflow.start_run(run_id=config.run_id) as run_context:
        training = TrainingModule()
        outputs = OutputsCollection()

        for qa_pair in batch:
            with mlflow.start_span(
                name=f"train_question_id_{qa_pair.id}",
                span_type="MODULE",
            ) as trace:
                # Process individual question
                # Log detailed metrics and traces

        # Log batch-level metrics
        mlflow.log_metrics({
            "batch_accuracy": outputs.mean_acc(),
            "batch_total_input_tokens": outputs.lm_metrics.input_tokens or 0,
            "batch_total_output_tokens": outputs.lm_metrics.output_tokens or 0,
            "batch_total_cost": outputs.lm_metrics.cost or 0.0,
            "batch_questions_processed": len(batch),
            "batch_duration_seconds": duration,
        }, step=config.batch_num)
```

#### 1.3 CLI Arguments
```python
parser.add_argument("--run-id", required=True, help="MLflow run ID to continue")
parser.add_argument("--experiment-name", required=True, help="MLflow experiment name")
parser.add_argument("--model", required=True, help="Model name")
parser.add_argument("--provider", required=True, help="Provider name")
parser.add_argument("--start-index", type=int, required=True, help="Start index in trainset")
parser.add_argument("--batch-size", type=int, default=30, help="Batch size")
parser.add_argument("--total-samples", type=int, required=True, help="Total training samples")
parser.add_argument("--batch-num", type=int, required=True, help="Current batch number")
parser.add_argument("--total-batches", type=int, required=True, help="Total number of batches")
```

### Phase 2: Main Training Script Updates

#### 2.1 Enhanced TrainingRunner Class
```python
class TrainingRunner:
    def __init__(self,
                 # ... existing parameters ...
                 batch_size: Optional[int] = None,
                 force_batches: bool = False,
                 continue_run: bool = False):
        # ... existing initialization ...
        self.batch_size = batch_size or (30 if self._should_use_batches() else None)
        self.force_batches = force_batches
        self.continue_run = continue_run
```

#### 2.2 Batch Processing Logic
```python
def _run_training_batches(self) -> Dict:
    """Run training in batches with process isolation."""
    total_batches = (len(self.trainset) + self.batch_size - 1) // self.batch_size

    successful_batches = 0
    failed_batches = 0

    for batch_num in range(total_batches):
        start_index = batch_num * self.batch_size

        max_retries = 3
        for attempt in range(max_retries):
            success = self._process_single_batch(
                batch_num=batch_num,
                start_index=start_index,
                total_batches=total_batches,
                attempt=attempt + 1
            )

            if success:
                successful_batches += 1
                break
            elif attempt < max_retries - 1:
                self.logger.warning(f"Batch {batch_num + 1} failed, restarting Python process")
                time.sleep(10)
            else:
                failed_batches += 1

    return self._compile_final_metrics(successful_batches, total_batches)
```

#### 2.3 Process Execution
```python
def _process_single_batch(self, batch_num: int, start_index: int,
                         total_batches: int, attempt: int) -> bool:
    """Process a single batch in a separate Python process."""

    cmd = [
        "uv", "run", "python", "scripts/run_training_batch.py",
        "--run-id", self.run_id,
        "--experiment-name", self.experiment_name,
        "--model", self.model_name,
        "--provider", self.provider_name,
        "--start-index", str(start_index),
        "--batch-size", str(self.batch_size),
        "--total-samples", str(len(self.trainset)),
        "--batch-num", str(batch_num + 1),
        "--total-batches", str(total_batches),
    ]

    import subprocess
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=3600,  # 1 hour timeout
        )

        return result.returncode == 0

    except subprocess.TimeoutExpired:
        self.logger.error(f"Batch {batch_num + 1} timed out after 1 hour")
        return False
```

### Phase 3: Resume Logic Implementation

#### 3.1 MLflow-Based Resume Detection
```python
def _get_most_recent_run_info(self) -> Optional[Dict[str, Any]]:
    """Get information about the most recent run to continue."""
    try:
        runs = mlflow.search_runs(
            experiment_names=[self.experiment_name],
            order_by=["start_time DESC"],
            max_results=1,
            output_format="list"
        )

        if not runs:
            return None

        latest_run = runs[0]
        run_id = latest_run.info.run_id

        # Get last processed question from traces
        last_question_id = self._get_last_question_id_from_traces(run_id)

        return {
            "run_id": run_id,
            "last_question_id": last_question_id,
            "status": latest_run.info.status,
            "start_time": latest_run.info.start_time
        }

    except Exception as e:
        self.logger.error(f"Failed to get recent run info: {e}")
        return None
```

#### 3.2 Question ID Extraction from Traces
```python
def _get_last_question_id_from_traces(self, run_id: str) -> Optional[int]:
    """Extract the last processed question ID from MLflow traces."""
    try:
        traces = mlflow.search_traces(
            run_id=run_id,
            filter_string="name LIKE 'train_question_id_%'",
            order_by=["start_time DESC"],
            max_results=1000,
            return_type="list"
        )

        question_ids = []
        for trace in traces:
            if trace.spans:
                span_name = trace.spans[0].name
                if span_name.startswith("train_question_id_"):
                    try:
                        question_id = int(span_name.split("_")[-1])
                        question_ids.append(question_id)
                    except (ValueError, IndexError):
                        continue

        return max(question_ids) if question_ids else None

    except Exception as e:
        self.logger.warning(f"Failed to get last question ID from traces: {e}")
        return None
```

#### 3.3 Resume Setup Logic
```python
def _setup_resume_or_new_run(self) -> Tuple[Optional[str], List[QA_Pair], bool]:
    """Setup run for resume or start new run."""
    if self.continue_run:
        recent_run_info = self._get_most_recent_run_info()

        if recent_run_info and recent_run_info["status"] != "FINISHED":
            run_id = recent_run_info["run_id"]
            last_question_id = recent_run_info["last_question_id"]

            self.logger.info(f"Found recent run: {run_id}")
            if last_question_id is not None:
                self.logger.info(f"Resuming from question_id {last_question_id}")
                trainset = self._prepare_resume_trainset(last_question_id)
            else:
                self.logger.info("No previous questions found, starting from beginning")
                trainset = self.trainset_full

            return run_id, trainset, True
        else:
            self.logger.warning("No suitable recent run found, starting new run")

    return None, self.trainset_full, False
```

### Phase 4: CLI Updates

#### 4.1 New Command Line Arguments
```python
parser.add_argument(
    "--continue",
    action="store_true",
    dest="continue_run",
    help="Continue the most recent run in the experiment (requires MLflow server)"
)

parser.add_argument(
    "--batch-size",
    type=int,
    default=None,
    help="Process training data in batches (default: 30 for large datasets, None for small datasets)"
)

parser.add_argument(
    "--force-batches",
    action="store_true",
    help="Force batched mode even for small datasets"
)
```

#### 4.2 Auto-Batch Detection
```python
def _should_use_batches(self) -> bool:
    """Determine if batched mode should be used."""
    if self.force_batches:
        return True
    # Auto-enable batches for large datasets (>100 samples)
    return len(self.trainset_full) > 100
```

## Usage Examples

### Basic Training with Batching
```bash
# Auto-enable batching for large datasets
uv run scripts/run_training.py --model glm-4.6 --provider zai --no-cache

# Force batching for small datasets
uv run scripts/run_training.py --model glm-4.6 --provider zai --force-batches --batch-size 30
```

### Resume Training
```bash
# Continue the most recent run
uv run scripts/run_training.py --continue --model glm-4.6 --provider zai

# Continue with custom batch size
uv run scripts/run_training.py --continue --model glm-4.6 --provider zai --batch-size 20
```

### Custom Experiment Names
```bash
# Resume from custom experiment
uv run scripts/run_training.py --continue --experiment-name "Custom_Training" --model glm-4.6 --provider zai
```

## Implementation Benefits

1. **Complete Memory Isolation**: Each batch runs in a fresh Python process, eliminating memory leaks
2. **MLflow Reliability**: All state tracking via MLflow traces (no local dependencies)
3. **Training Focus**: Removed optimizer and evaluation for clean separation of concerns
4. **Robust Error Handling**: Failed batches trigger process restart and retry (up to 3 times)
5. **Comprehensive Logging**: Both console output and MLflow metrics after each batch
6. **Fixed Batch Size**: 30 questions per batch as requested
7. **Resume Capability**: Can resume from any point in training based on MLflow traces

## Error Handling Strategy

### MLflow Connection Validation
- Fail fast if MLflow server is unavailable
- Validate experiment existence before starting

### Batch Failure Handling
- Up to 3 retries per batch with process restart
- 1-hour timeout per batch
- Detailed error logging for debugging

### Resume Logic Robustness
- Multiple fallback strategies for finding last processed question
- Graceful degradation if trace analysis fails
- Clear logging of resume decisions

## Testing Strategy

1. **Unit Tests**: Test resume logic with mock MLflow data
2. **Integration Tests**: Test batch worker script with small datasets
3. **End-to-End Tests**: Test full training pipeline with resume scenarios
4. **Memory Tests**: Verify memory usage stays stable across batches

## Migration Notes

- Existing training runs will continue to work with single-process mode
- New CLI arguments are optional with sensible defaults
- MLflow server must be running for resume functionality
- No changes required to existing database schema

## Future Enhancements

1. **Adaptive Batch Sizes**: Adjust batch size based on memory usage
2. **Parallel Processing**: Run multiple batches in parallel (if memory permits)
3. **Smart Resume**: Resume from specific questions rather than just last processed
4. **Progress Dashboard**: Web-based progress tracking for long-running training

## Dependencies

- Python 3.12+
- MLflow server running on http://127.0.0.1:5000
- UV package manager
- All existing IFC Answer Engine dependencies

---

*This plan provides a comprehensive solution to the memory leak issues while adding robust resume capabilities and maintaining full MLflow integration.*