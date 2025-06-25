import os
import sqlite3
from datetime import datetime
from sqlite3 import Connection
from typing import Optional, Literal, List

import pandas as pd
from dotenv import find_dotenv, load_dotenv
from pydantic import BaseModel

from src.config import DB_PATH

load_dotenv(find_dotenv())


def datetime_encoder(dt: datetime) -> str:
    """
    Encode a python datetime object to an ISO 8601 formated string.
    """
    return dt.isoformat("-")


def datetime_decoder(s: bytes) -> datetime:
    """
    Decode an ISO 8601 formated bytestring into a python datetime object.
    """
    return datetime.fromisoformat(s.decode())


# Register the encoder and decoder into the db
sqlite3.register_adapter(datetime, datetime_encoder)
sqlite3.register_converter("timestamp", datetime_decoder)


class DatasetRow(BaseModel):
    id: Optional[int] = None
    question: Optional[str] = None
    answer: Optional[str] = None
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
    id: Optional[int] = None
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
    """Return a connection to the database"""
    return sqlite3.connect(
        DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
    )


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
                dataset.answer = result[2]
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
                run.timestamp = result[6]
            except Exception as e:
                print(f"Error while trying to fetch the run with id: {id}\nError: {e}")
                pass

        return run


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
                log.timestamp = result[4]
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


def get_last_log_id(run_id: int) -> int:
    """
    Return the id of the lattest row in the logs table for a given run_id, or 0 if no rows exist for the provided id.
    """
    with connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT MAX(id) FROM logs WHERE run_id = ?
            """,
            (run_id,),
        )
        last_row_id = cursor.fetchone()[0]

    return last_row_id or 0


def get_tokens_count_logs(run_id: int) -> tuple[int, int]:
    """
    Returns the sums of input_tokens and output_tokens of logs for a given run_id.
    """
    with connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                SUM(input_tokens) as total_input_tokens,
                SUM(output_tokens) as total_output_tokens
            FROM logs
            WHERE run_id = ?
            """,
            (run_id,),
        )
        result = cursor.fetchone()
        total_input_tokens = result[0] or 0
        total_output_tokens = result[1] or 0

    return total_input_tokens, total_output_tokens


def insert_new_ifc_model(ifc_model: IfcModelRow) -> int:
    """
    Inserts a new ifc model into the ifc_models table and returns the ID of the inserted model or 0 if none is generated.
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

        conn.commit()
        return cursor.lastrowid or 0


def insert_new_dataset_row(dataset: DatasetRow) -> int:
    """
    Inserts a new row into the dataset table and returns the ID of the inserted row or 0 if no row is inserted.
    The ID will be generated by the database automatically.
    """

    with connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO dataset (question, ground_truth, ifc_id)
            VALUES (?, ?, ?)
            """,
            (dataset.question, dataset.answer, dataset.ifc_id),
        )

        conn.commit()
        return cursor.lastrowid or 0


def insert_new_run(new_run: RunsRow) -> int:
    """
    Inserts a new run into the runs table and returns the ID of the inserted run or 0 if no row is inserted.
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


def insert_new_log(new_log: LogRow) -> int:
    """
    Insert a new log into the logs table and return the ID of the inserted run or 0 if no row is inserted.
    The ID will be generated by the database automatically.
    """
    with connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO logs (run_id, agent_name, step_number, timestamp, model_output, action_input_code, action_output, observations, error, duration, input_tokens, output_tokens)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_log.run_id,
                new_log.agent_name,
                new_log.step_number,
                new_log.timestamp,
                new_log.model_output,
                new_log.action_input_code,
                new_log.action_output,
                new_log.observations,
                new_log.error,
                new_log.duration,
                new_log.input_tokens,
                new_log.output_tokens,
            ),
        )

        conn.commit()
        return cursor.lastrowid or 0


def empty_table(table_name: Literal["dataset", "ifc_models", "logs", "runs"]) -> None:
    """
    Delete all row of the selected table.
    """
    with connection() as conn:
        cursor = conn.cursor()
        # Temporarily disable foreign key constraints
        cursor.execute("PRAGMA foreign_keys = OFF")
        cursor.execute(f"DELETE FROM {table_name}")
        # Re-enable foreign key constraints
        cursor.execute("PRAGMA foreign_keys = ON")
        conn.commit()


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


def get_ifc_models(
    id: Optional[int] = None,
    project_name: Optional[str] = None,
    model_name: Optional[str] = None,
) -> List[IfcModelRow]:
    """
    Returns a list of IfcModelRow pydantic objects with the values of all rows from the database
    that match the provided criteria (id, project_name, and/or model_name).
    If no matching rows are found, returns an empty list.
    """
    with connection() as db_conn:
        cursor = db_conn.cursor()

        # Build dynamic query based on provided parameters
        conditions = []
        params = []

        if id is not None:
            conditions.append("id = ?")
            params.append(id)

        if project_name is not None:
            conditions.append("project_name = ?")
            params.append(project_name)

        if model_name is not None:
            conditions.append("model_name = ?")
            params.append(model_name)

        # If no conditions provided, return all models
        if not conditions:
            query = "SELECT * FROM ifc_models"
            cursor.execute(query)
        else:
            query = f"SELECT * FROM ifc_models WHERE {' AND '.join(conditions)}"
            cursor.execute(query, params)

        results = cursor.fetchall()
        ifc_models = []

        for result in results:
            ifc_model = IfcModelRow()
            try:
                ifc_model.id = result[0]
                ifc_model.project_name = result[1]
                ifc_model.model_name = result[2]
                ifc_model.model_path = result[3]
                ifc_model.model_description = result[4]
                ifc_models.append(ifc_model)
            except Exception as e:
                print(
                    f"Error while trying to fetch the ifc model with id: {id}, project_name: {project_name}, model_name: {model_name}\nError: {e}"
                )
                continue

        return ifc_models


def main():
    """Initialize database and populate with data."""
    try:
        from src.config import (
            DATASET_PATH,
            CSV_IFC_MODELS_PATH,
            DIRECTORY_IFC_MODELS_PATH,
        )
    except ImportError:
        print(
            "Warning: Could not import config. Make sure you're running from the correct directory."
        )
        return

    init_sqlite_db()
    print("DB initialize successfully\n")

    # Drop and recreate all tables to ensure a clean slate
    drop_and_recreate_tables()
    print("Tables dropped and recreated successfully\n")

    # Populate these tables using the Excel files
    # Ifc models
    ifc_models = pd.read_csv(filepath_or_buffer=CSV_IFC_MODELS_PATH)
    for row in ifc_models.itertuples(name="ifc_models"):
        ifc_model = IfcModelRow(
            project_name=row.project_name,  # type: ignore
            model_name=row.model_name,  # type: ignore
            model_path=os.path.join(
                DIRECTORY_IFC_MODELS_PATH,
                row.project_name,  # type: ignore
                f"{row.model_name}.ifc",  # type: ignore
            ),
            model_description=row.model_description,  # type: ignore
        )
        insert_new_ifc_model(ifc_model=ifc_model)

    # Dataset
    dataset = pd.read_csv(filepath_or_buffer=DATASET_PATH)
    for row in dataset.itertuples(name="dataset"):
        ifc_models_list = get_ifc_models(
            project_name=row.project,  # type: ignore
            model_name=row.ifc_model,  # type: ignore
        )
        for model in ifc_models_list:
            if model.id is None:
                print(
                    f"Could not find a corresponding model for project: "
                    f"{row.project} and model: {row.ifc_model}"  # type: ignore
                )
                continue

            new_row = DatasetRow(
                question=row.question,  # type: ignore
                answer=row.answer,  # type: ignore
                ifc_id=model.id,
            )

            insert_new_dataset_row(dataset=new_row)

    print("END")


if __name__ == "__main__":
    main()
