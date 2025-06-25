"""Database module for experiment tracking and data management."""

# Import models
from .models import (
    DatasetRow,
    RunsRow,
    IfcModelRow,
    LogRow,
    DateTimeEncoder,
    datetime_encoder,
    datetime_decoder,
)

# Import database creation and schema functions
from .create_db import (
    init_sqlite_db,
    connection,
    drop_and_recreate_tables,
    empty_table,
)

# Import query functions
from .query_db import (
    get_dataset_row,
    get_run_row,
    get_log_row,
    get_last_log_id,
    get_tokens_count_logs,
    get_ifc_models,
)

# Import update functions
from .update_db import (
    insert_new_ifc_model,
    insert_new_dataset_row,
    insert_new_run,
    insert_new_log,
)

# Import population functions
from .populate_db import (
    populate_database,
)

__all__ = [
    # Models
    "DatasetRow",
    "RunsRow",
    "IfcModelRow",
    "LogRow",
    "DateTimeEncoder",
    "datetime_encoder",
    "datetime_decoder",
    # Database creation
    "init_sqlite_db",
    "connection",
    "drop_and_recreate_tables",
    "empty_table",
    # Query functions
    "get_dataset_row",
    "get_run_row",
    "get_log_row",
    "get_last_log_id",
    "get_tokens_count_logs",
    "get_ifc_models",
    # Update functions
    "insert_new_ifc_model",
    "insert_new_dataset_row",
    "insert_new_run",
    "insert_new_log",
    # Population functions
    "populate_database",
]
