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
    id: Optional[int] = None
    question_id: Optional[int] = None
    llm: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    duration: Optional[float] = None
    timestamp: Optional[datetime] = None


class IfcModelRow(BaseModel):
    id: Optional[int] = None
    project_name: Optional[str] = None
    model_name: Optional[str] = None
    model_path: Optional[str] = None
    model_description: Optional[str] = None


class LogRow(BaseModel):
    id: int
    run_id: Optional[int] = None
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
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (question_id) REFERENCES dataset(id)
            )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
      		run_id INTEGER,
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
                run.question_id = result[1]
                run.llm = result[2]
                run.input_tokens = result[3]
                run.output_tokens = result[4]
                run.duration = result[5]
                run.timestamp = datetime.fromisoformat(result[6]) if result[6] else None
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
                log.agent_name = result[2]
                log.step_number = result[3]
                log.timestamp = datetime.fromisoformat(result[4]) if result[4] else None
                log.model_output = result[5]
                log.action_input_code = result[6]
                log.action_output = result[7]
                log.observations = result[8]
                log.error = result[9]
                log.duration = result[10]
                log.input_tokens = result[11]
                log.output_tokens = result[12]
            except Exception as e:
                print(f"Error while trying to fetch the log with id: {id}\nError: {e}")
                pass

        return log


def insert_new_run(new_run: RunsRow) -> int:
    """
    Inserts a new run into the runs table and returns the ID of the inserted run.
    The ID will be generated by the database automatically.
    """
    with connection() as db_conn:
        cursor = db_conn.cursor()
        cursor.execute(
            """
            INSERT INTO runs (question_id, llm, input_tokens, output_tokens, duration, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (
                new_run.question_id,
                new_run.llm,
                new_run.input_tokens,
                new_run.output_tokens,
                new_run.duration,
                new_run.timestamp or datetime.now(),
            ),
        )
        db_conn.commit()
        return cursor.lastrowid or 0


def insert_new_ifc_model(ifc_model: IfcModelRow):
    """
    Inserts a new ifc model into the ifc_models table and returns the ID of the inserted model.
    The ID will be generated by the database automatically.
    """
    with connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO ifc_models (project_name, model_name, model_path, model_description)
            VALUES (?, ?, ?, ?)
            """,
            (
                ifc_model.project_name,
                ifc_model.model_name,
                ifc_model.model_path,
                ifc_model.model_description,
            ),
        )


if __name__ == "__main__":
    import json

    init_sqlite_db()
    print("DB initialize successfully\n\n")

    # Create new ifc model
    new_ifc_model = IfcModelRow(
        model_name="arc",
        project_name="duplex",
        model_path="src/bim_models/duplex/arc.ifc",
        model_description="The architectural model of a house project, with 2 twin houses.",
    )
    new_model_id = insert_new_ifc_model(ifc_model=new_ifc_model)
    print(f"New ifc model added with id = {new_ifc_model}")

    # Example of creating a new run
    new_run = RunsRow(
        llm="gpt-4",
        input_tokens=1024,
        output_tokens=512,
        duration=2.5,
        timestamp=datetime.now(),
    )
    new_run_id = insert_new_run(new_run)
    print(f"Created new run with ID: {new_run_id}")

    # Verify the new run was created
    inserted_run = get_run_row(new_run_id)
    print(f"Newly inserted run: {inserted_run}")

    # Define a custom JSON encoder for datetime objects
    class DateTimeEncoder(json.JSONEncoder):
        def default(self, o):
            if isinstance(o, datetime):
                return o.isoformat()
            return super().default(o)

    print(
        f"Row from dataset with id == 1: {json.dumps(get_dataset_row(1).model_dump(), indent=2, cls=DateTimeEncoder)}"
    )
    print(
        f"Row from runs with id == 1: {json.dumps(get_run_row(1).model_dump(), indent=2, cls=DateTimeEncoder)}"
    )
    print(
        f"Row from logs with id == 1: {json.dumps(get_log_row(1).model_dump(), indent=2, cls=DateTimeEncoder)}"
    )
    print(
        f"Row from ifc_models with id == 1: {json.dumps(get_ifc_model_row(1).model_dump(), indent=2, cls=DateTimeEncoder)}"
    )
