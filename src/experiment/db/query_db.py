"""Database query functions."""

from typing import List, Optional

try:
    # Try relative imports first (when imported as module)
    from .create_db import connection
    from .models import DatasetRow, RunsRow, LogRow, IfcModelRow
except ImportError:
    # Fall back to absolute imports (when run as script)
    from src.experiment.db.create_db import connection
    from src.experiment.db.models import DatasetRow, RunsRow, LogRow, IfcModelRow


def get_dataset_row(id: int) -> DatasetRow:
    """
    Returns a Dataset pydantic object with the values of the rows from the database for the given id.
    If the id is invalid, the Dataset object will only contain 0 for integers and "" for str.
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
                    f"Error while trying to fetch the question with id: {id}\nError: {e}"
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
    Return the id of the latest row in the logs table for a given run_id, or 0 if no rows exist for the provided id.
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
