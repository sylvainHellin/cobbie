import sqlite3
from sqlite3 import Connection
from pydantic import BaseModel

from config import DB_NAME


class DatasetRow(BaseModel):
    id: int = 0
    question: str = ""
    ground_truth: str = ""
    ifc_id: int = 0


def init_sqlite_db():
    global db_conn, previous_agent_token_counts
    previous_agent_token_counts = {}  # Reset for each script run / DB init
    db_conn = sqlite3.connect(DB_NAME)
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
        project_name TEXT,
        ifc_id INT NOT NULL,
        FOREIGN KEY (ifc_id) REFERENCES ifc_models(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        question_id INT,
        llm TEXT,
        agent_name TEXT,
        step_number INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        model_output TEXT,
        action_input_code TEXT,
        action_output TEXT,
        observations TEXT,
        error TEXT,
        duration_s REAL,
        input_tokens INTEGER,
        output_tokens INTEGER,
        FOREIGN KEY (question_id) REFERENCES dataset(id)
    )
    """)
    db_conn.commit()


def connection() -> Connection:
    """Return a connection to the database"""
    return sqlite3.connect(DB_NAME)


def get_dataset_row_by_id(question_id: int) -> DatasetRow:
    """
    Returns a Dataset pydantic object with the values of the rows from the database for the given id. If the id is invalid, the Dataset object will only contain 0 for integers and "" for str.
    """
    with connection() as db_conn:
        cursor = db_conn.cursor()
        cursor.execute("SELECT * FROM dataset WHERE id = ?", (question_id,))
        result = cursor.fetchone()
        dataset = DatasetRow()
        if result is not None:
            try:
                dataset.id = result[0]
                dataset.question = result[1]
                dataset.ground_truth = result[2]
                dataset.ifc_id = result[4]
            except Exception as e:
                print(
                    f"Error while trying to fetch the questio with id: {question_id}\nError: {e}"
                )
                pass

        return dataset


if __name__ == "__main__":
    init_sqlite_db()
    print("DB initialize successfully\n\n")

    print(f"Row from dataset with id == 1: {get_dataset_row_by_id(1)}")
