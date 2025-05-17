import os
import sqlite3
from datetime import datetime
from sqlite3 import Connection
from typing import Optional

from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel

load_dotenv(find_dotenv())

DB_PATH = os.environ["DB_PATH"]


class DatasetRow(BaseModel):
    id: int
    question: Optional[str] = None
    ground_truth: Optional[str] = None
    ifc_id: Optional[int] = None


class RunsRow(BaseModel):
    id: int
    llm: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    duration: Optional[float] = None
    timestamp: Optional[datetime] = None


class IfcModelRow(BaseModel):
    id: int
    project_name: Optional[str] = None
    model_name: Optional[str] = None
    model_path: Optional[str] = None
    model_description: Optional[str] = None


class LogRow(BaseModel):
    id: int
    run_id: Optional[int] = None
    question_id: Optional[int] = None
    agent_name: Optional[str] = None
    step_number: Optional[int] = None
    timestamp: Optional[datetime] = None
    model_output: Optional[str] = None
    action_input_code: Optional[str] = None
    action_output: Optional[str] = None
    observations: Optional[str] = None
    error: Optional[str] = None
    duration: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


def init_sqlite_db():
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
        ifc_id INT NOT NULL,
        FOREIGN KEY (ifc_id) REFERENCES ifc_models(id)
    )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        llm TEXT,
        input_tokens INT,
        output_tokens INT,
        duration REAL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
      		run_id INTEGER,
            question_id INTEGER,
            agent_name TEXT,
            step_number INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            model_output TEXT,
            action_input_code TEXT,
            action_output TEXT,
            observations TEXT,
            error TEXT,
            duration REAL,
            input_tokens INTEGER,
            output_tokens INTEGER,
            FOREIGN KEY (question_id) REFERENCES dataset(id)
            FOREIGN KEY (run_id) REFERENCES runs(id)
            )
    """)

    db_conn.commit()


def connection() -> Connection:
    """Return a connection to the database"""
    return sqlite3.connect(DB_PATH)


def get_dataset_row(id: int) -> DatasetRow:
    """
    Returns a Dataset pydantic object with the values of the rows from the database for the given id. If the id is invalid, the Dataset object will only contain 0 for integers and "" for str.
    """
    with connection() as db_conn:
        cursor = db_conn.cursor()
        cursor.execute("SELECT * FROM dataset WHERE id = ?", (id,))
        result = cursor.fetchone()
        dataset = DatasetRow(id=id)
        if result is not None:
            try:
                dataset.id = result[0]
                dataset.question = result[1]
                dataset.ground_truth = result[2]
                dataset.ifc_id = result[3]
            except Exception as e:
                print(
                    f"Error while trying to fetch the questio with id: {id}\nError: {e}"
                )
                pass

        return dataset


def get_run_row(id: int) -> RunsRow:
    """
    Returns a RunsRow pydantic object with the values of the rows from the database for the given id.
    If the id is invalid, the RunsRow object will only contain the id.
    """
    with connection() as db_conn:
        cursor = db_conn.cursor()
        cursor.execute("SELECT * FROM runs WHERE id = ?", (id,))
        result = cursor.fetchone()
        run = RunsRow(id=id)
        if result is not None:
            try:
                run.id = result[0]
                run.llm = result[1]
                run.input_tokens = result[2]
                run.output_tokens = result[3]
                run.duration = result[4]
                run.timestamp = datetime.fromisoformat(result[5]) if result[5] else None
            except Exception as e:
                print(f"Error while trying to fetch the run with id: {id}\nError: {e}")
                pass

        return run


def get_ifc_model_row(id: int) -> IfcModelRow:
    """
    Returns an IfcModelRow pydantic object with the values of the rows from the database for the given id.
    If the id is invalid, the IfcModelRow object will only contain the id.
    """
    with connection() as db_conn:
        cursor = db_conn.cursor()
        cursor.execute("SELECT * FROM ifc_models WHERE id = ?", (id,))
        result = cursor.fetchone()
        ifc_model = IfcModelRow(id=id)
        if result is not None:
            try:
                ifc_model.id = result[0]
                ifc_model.project_name = result[1]
                ifc_model.model_name = result[2]
                ifc_model.model_path = result[3]
                ifc_model.model_description = result[4]
            except Exception as e:
                print(
                    f"Error while trying to fetch the ifc model with id: {id}\nError: {e}"
                )
                pass

        return ifc_model


def get_log_row(id: int) -> LogRow:
    """
    Returns a LogRow pydantic object with the values of the rows from the database for the given id.
    If the id is invalid, the LogRow object will only contain the id.
    """
    with connection() as db_conn:
        cursor = db_conn.cursor()
        cursor.execute("SELECT * FROM logs WHERE id = ?", (id,))
        result = cursor.fetchone()
        log = LogRow(id=id)
        if result is not None:
            try:
                log.id = result[0]
                log.run_id = result[1]
                log.question_id = result[2]
                log.agent_name = result[3]
                log.step_number = result[4]
                log.timestamp = datetime.fromisoformat(result[5]) if result[5] else None
                log.model_output = result[6]
                log.action_input_code = result[7]
                log.action_output = result[8]
                log.observations = result[9]
                log.error = result[10]
                log.duration = result[11]
                log.input_tokens = result[12]
                log.output_tokens = result[13]
            except Exception as e:
                print(f"Error while trying to fetch the log with id: {id}\nError: {e}")
                pass

        return log


if __name__ == "__main__":
    import json

    init_sqlite_db()
    print("DB initialize successfully\n\n")

    print(
        f"Row from dataset with id == 1: {json.dumps(get_dataset_row(1).model_dump(), indent=2)}"
    )
    print(
        f"Row from runs with id == 1: {json.dumps(get_run_row(1).model_dump(), indent=2)}"
    )
    print(
        f"Row from logs with id == 1: {json.dumps(get_log_row(1).model_dump(), indent=2)}"
    )
    print(
        f"Row from ifc_models with id == 1: {json.dumps(get_ifc_model_row(1).model_dump(), indent=2)}"
    )
