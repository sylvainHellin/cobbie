"""Database creation and schema management."""

import sqlite3
from sqlite3 import Connection

from src.config import DB_PATH

# Global variables for database connection
db_conn = None
previous_agent_token_counts = {}


def init_sqlite_db():
    """Initialize the SQLite database with all required tables."""
    global db_conn, previous_agent_token_counts
    previous_agent_token_counts = {}  # Reset for each script run / DB init
    db_conn = sqlite3.connect(DB_PATH)
    cursor = db_conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ifc_models (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_name TEXT NOT NULL,
        model_name TEXT NOT NULL,
        model_path TEXT NOT NULL,
        model_description TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS dataset (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        question TEXT NOT NULL,
        ground_truth TEXT NOT NULL,
        ifc_id INTEGER NOT NULL,
        FOREIGN KEY (ifc_id) REFERENCES ifc_models(id)
    )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_id INTEGER,
            llm TEXT,
            input_tokens INTEGER,
            output_tokens INTEGER,
            duration REAL,
            timestamp timestamp,
            FOREIGN KEY (question_id) REFERENCES dataset(id)
            )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
      		run_id INTEGER,
            agent_name TEXT,
            step_number INTEGER,
            timestamp timestamp,
            model_output TEXT,
            action_input_code TEXT,
            action_output TEXT,
            observations TEXT,
            error TEXT,
            duration REAL,
            input_tokens INTEGER,
            output_tokens INTEGER,
            FOREIGN KEY (run_id) REFERENCES runs(id)
            )
    """)

    db_conn.commit()


def connection() -> Connection:
    """Return a connection to the database."""
    return sqlite3.connect(
        DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
    )


def drop_and_recreate_tables() -> None:
    """
    Drop all tables and recreate them with the correct schema.
    """
    with connection() as conn:
        cursor = conn.cursor()

        # Drop tables in reverse dependency order
        cursor.execute("DROP TABLE IF EXISTS logs")
        cursor.execute("DROP TABLE IF EXISTS runs")
        cursor.execute("DROP TABLE IF EXISTS dataset")
        cursor.execute("DROP TABLE IF EXISTS ifc_models")

        # Recreate tables with the same schema as init_sqlite_db
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS ifc_models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name TEXT NOT NULL,
            model_name TEXT NOT NULL,
            model_path TEXT NOT NULL,
            model_description TEXT NOT NULL
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS dataset (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            ground_truth TEXT NOT NULL,
            ifc_id INTEGER NOT NULL,
            FOREIGN KEY (ifc_id) REFERENCES ifc_models(id)
        )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER,
                llm TEXT,
                input_tokens INTEGER,
                output_tokens INTEGER,
                duration REAL,
                timestamp timestamp,
                FOREIGN KEY (question_id) REFERENCES dataset(id)
                )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
          		run_id INTEGER,
                agent_name TEXT,
                step_number INTEGER,
                timestamp timestamp,
                model_output TEXT,
                action_input_code TEXT,
                action_output TEXT,
                observations TEXT,
                error TEXT,
                duration REAL,
                input_tokens INTEGER,
                output_tokens INTEGER,
                FOREIGN KEY (run_id) REFERENCES runs(id)
                )
        """)

        conn.commit()


def empty_table(table_name: str) -> None:
    """
    Empty the specified table by deleting all rows.

    Args:
        table_name: Name of the table to empty
    """
    with connection() as conn:
        cursor = conn.cursor()
        cursor.execute(f"DELETE FROM {table_name}")
        conn.commit()
