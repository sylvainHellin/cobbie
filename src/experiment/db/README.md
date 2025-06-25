# Database Module

This directory contains a modular database system for experiment tracking and data management. The database functionality has been separated into focused modules for better maintainability and follows the single responsibility principle.

## File Structure

```
src/experiment/db/
├── README.md              # This file
├── __init__.py           # Module exports and imports
├── models.py             # Data models and utility functions
├── create_db.py          # Database initialization and schema management
├── query_db.py           # Database query functions
├── update_db.py          # Database insert and update functions
├── populate_db.py        # Initial data population script
├── example_usage.py      # Usage examples and demonstrations
├── db_old.py            # Original monolithic db.py (backup)
├── db.db                # SQLite database file
└── ifc_models.csv       # IFC models metadata
```

## Module Overview

### 🏗️ `models.py`
Contains all data models and utility functions:

- **Data Classes**: `DatasetRow`, `RunsRow`, `IfcModelRow`, `LogRow`
- **Utilities**: `datetime_encoder`, `datetime_decoder`, `DateTimeEncoder`
- **SQLite Adapters**: Automatic datetime conversion for database storage

### 🔧 `create_db.py`
Database creation and schema management:

- `init_sqlite_db()` - Initialize database with all tables
- `connection()` - Get database connection
- `drop_and_recreate_tables()` - Clean slate database reset
- `empty_table()` - Clear specific table contents

### 🔍 `query_db.py`
All database query functions:

- `get_dataset_row()` - Retrieve dataset entries
- `get_run_row()` - Retrieve experiment runs
- `get_log_row()` - Retrieve log entries
- `get_ifc_models()` - Search and filter IFC models
- `get_last_log_id()` - Get latest log ID for a run
- `get_tokens_count_logs()` - Aggregate token usage statistics

### 📝 `update_db.py`
Database insert and update operations:

- `insert_new_ifc_model()` - Add new IFC model
- `insert_new_dataset_row()` - Add new dataset entry
- `insert_new_run()` - Create new experiment run
- `insert_new_log()` - Add log entry to a run
- `empty_table()` - Clear table contents

### 🌱 `populate_db.py`
Initial data population script:

- `populate_database()` - Load initial data from CSV files
- Can be run standalone: `PYTHONPATH=. python src/experiment/db/populate_db.py`
- Handles both relative and absolute imports

## Usage Examples

### Basic Import
```python
from src.experiment.db import (
    init_sqlite_db,
    get_ifc_models,
    insert_new_run,
    DatasetRow,
    RunsRow,
)
```

### Initialize Database
```python
from src.experiment.db import init_sqlite_db, populate_database

# Initialize schema
init_sqlite_db()

# Populate with initial data
populate_database()
```

### Query Data
```python
from src.experiment.db import get_ifc_models, get_dataset_row

# Get all IFC models
all_models = get_ifc_models()

# Search specific models
duplex_models = get_ifc_models(project_name="duplex")
arc_models = get_ifc_models(model_name="arc")

# Get specific dataset entry
dataset_entry = get_dataset_row(id=1)
```

### Insert Data
```python
from src.experiment.db import insert_new_run, RunsRow
from datetime import datetime

# Create new experiment run
new_run = RunsRow(
    question_id=1,
    llm="gpt-4",
    input_tokens=150,
    output_tokens=75,
    duration=2.5,
    timestamp=datetime.now(),
)

run_id = insert_new_run(new_run)
```

### Track Experiment Logs
```python
from src.experiment.db import insert_new_log, LogRow

# Add log entry
log_entry = LogRow(
    run_id=run_id,
    agent_name="query_agent",
    step_number=1,
    timestamp=datetime.now(),
    model_output="Processing IFC model...",
    action_input_code="parser.get_elements('IfcWall')",
    action_output="Found 24 walls",
    observations="Successfully identified wall elements",
    duration=0.8,
    input_tokens=50,
    output_tokens=25,
)

log_id = insert_new_log(log_entry)
```

## Running Scripts

### Populate Database
```bash
# From project root
PYTHONPATH=. python src/experiment/db/populate_db.py
```

### Run Examples
```bash
# From project root  
PYTHONPATH=. python src/experiment/db/example_usage.py
```

## Database Schema

### Tables

1. **ifc_models** - IFC model metadata
   - `id` (INTEGER PRIMARY KEY)
   - `project_name` (TEXT)
   - `model_name` (TEXT)
   - `model_path` (TEXT)
   - `model_description` (TEXT)

2. **dataset** - Question-answer pairs
   - `id` (INTEGER PRIMARY KEY)
   - `question` (TEXT)
   - `ground_truth` (TEXT)
   - `ifc_id` (INTEGER, FK to ifc_models)

3. **runs** - Experiment runs
   - `id` (INTEGER PRIMARY KEY)
   - `question_id` (INTEGER, FK to dataset)
   - `llm` (TEXT)
   - `input_tokens` (INTEGER)
   - `output_tokens` (INTEGER)
   - `duration` (REAL)
   - `timestamp` (TIMESTAMP)

4. **logs** - Detailed execution logs
   - `id` (INTEGER PRIMARY KEY)
   - `run_id` (INTEGER, FK to runs)
   - `agent_name` (TEXT)
   - `step_number` (INTEGER)
   - `timestamp` (TIMESTAMP)
   - `model_output` (TEXT)
   - `action_input_code` (TEXT)
   - `action_output` (TEXT)
   - `observations` (TEXT)
   - `error` (TEXT)
   - `duration` (REAL)
   - `input_tokens` (INTEGER)
   - `output_tokens` (INTEGER)

## Benefits of Modular Structure

1. **Separation of Concerns** - Each module has a single responsibility
2. **Easy Testing** - Individual modules can be tested in isolation
3. **Better Maintainability** - Changes to one area don't affect others
4. **Cleaner Imports** - Import only what you need
5. **No Import Warnings** - Proper module structure eliminates runtime warnings
6. **Scalability** - Easy to extend with new functionality

## Migration from Old Structure

The original `db.py` has been renamed to `db_old.py` for reference. All functionality has been preserved and distributed across the new modules. Update your imports as follows:

```python
# Old import
from src.experiment.db.db import get_ifc_models, insert_new_run

# New import
from src.experiment.db import get_ifc_models, insert_new_run
```

The `__init__.py` file ensures backward compatibility by exposing all the same functions and classes.