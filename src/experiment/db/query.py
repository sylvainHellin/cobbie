"""
Note: if making any changes in the DB directly, first run:
```zsh
sqlacodegen sqlite:///src/experiment/db/db.db --generator sqlmodels --outfile src/experiment/db/experiment_models.py
sqlacodegen sqlite:///mlflow.sqlite --generator sqlmodels --outfile src/experiment/db/mlflow_models.py
```
"""

from datetime import datetime
from functools import wraps
from typing import Callable, List, Optional, TypeVar

from sqlalchemy.orm import selectinload
from sqlmodel import Session, col, select

from src.experiment.db import EXPERIMENT_DB_ENGINE, MLFLOW_DB_ENGINE
from src.experiment.db.experiment_models import (
    Dataset,
    Experiment,
    Ifcmodels,
    Run,
    Trace,
)
from src.experiment.db.mlflow_models import Experiments, Runs

T = TypeVar("T")


def with_session(func: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator that automatically provides a database session as the first argument
    to the decorated function and handles session management.
    """

    @wraps(func)
    def wrapper(*args, **kwargs) -> T:
        with Session(EXPERIMENT_DB_ENGINE) as session:
            return func(session, *args, **kwargs)

    return wrapper


def get_dataset(
    limit: Optional[int] = None,
    load_ifc_model: bool = False,
) -> List[Dataset]:
    """
    Return the whole dataset as a List of Dataset
    """

    with Session(EXPERIMENT_DB_ENGINE) as session:
        # base select statement
        statement = select(Dataset).order_by(col(Dataset.id).asc())

        # limit if limit provided
        if limit:
            statement = statement.limit(limit)

        # Eager loading of the relationship
        if load_ifc_model:
            statement = statement.options(selectinload(getattr(Dataset, "ifc")))

        dataset = [row for row in session.exec(statement)]
        return dataset


def import_mlflow_experiments():
    """
    Mirrors the experiment from the mlflow db to the experiment db.
    """
    with Session(EXPERIMENT_DB_ENGINE) as db_session:
        with Session(MLFLOW_DB_ENGINE) as mlflow_session:
            # get ids of existing experiments in the experiment db
            existing_ids = {exp.id for exp in db_session.exec(select(Experiment)).all()}

            # Get the experiments from mlflow
            results = [exp for exp in mlflow_session.exec(select(Experiments))]

            # Loop through the experiment to add the missing ones
            for res in results:
                if (
                    res.experiment_id is not None
                    and res.name is not None
                    and str(res.experiment_id) not in existing_ids
                ):
                    exp = Experiment(
                        id=str(res.experiment_id),
                        name=res.name,
                    )
                    db_session.add(exp)

            # Commit the added experiments
            db_session.commit()


def import_mlflow_runs():
    """
    Mirrors the runs from the mlflow db to the experiment db.
    """
    with Session(EXPERIMENT_DB_ENGINE) as db_session:
        with Session(MLFLOW_DB_ENGINE) as mlflow_session:
            # Get the runs from mlflow
            mlflow_runs = [run for run in mlflow_session.exec(select(Runs))]

            # Get the runs from the experiment DB
            db_runs = {run.id: run for run in db_session.exec(select(Run))}

            # Loop through the experiment to add the missing ones
            for mlflow_run in mlflow_runs:
                if mlflow_run.run_uuid is not None and mlflow_run.name is not None:
                    # extract the metrics of this run
                    metrics = {
                        metric.key: metric.value for metric in mlflow_run.metrics
                    }

                    # Compute the timestamp
                    timestamp = (
                        datetime.fromtimestamp(mlflow_run.start_time / 1000)
                        if mlflow_run.start_time is not None
                        else None
                    )

                    # Compute the duration
                    duration = (
                        mlflow_run.end_time - mlflow_run.start_time
                        if (mlflow_run.end_time and mlflow_run.start_time)
                        else 0
                    )

                    # extract the other fields
                    id = mlflow_run.run_uuid
                    experiment_id = str(mlflow_run.experiment_id)
                    name = mlflow_run.name
                    url = f"http://127.0.0.1:5000/#/experiments/{mlflow_run.experiment_id}/runs/{mlflow_run.run_uuid}"

                    cost = metrics.get("cost")
                    accuracy = metrics.get("accuracy")
                    input_tokens = int(metrics.get("input_tokens", 0))
                    output_tokens = int(metrics.get("output_tokens", 0))

                    # Try to get the run from the db_runs
                    run = db_runs.get(id, None)

                    # If the run don't already exist, create it
                    if run is None:
                        run = Run(
                            id=id,
                            experiment_id=experiment_id,
                        )

                    # Now, update all the fields
                    run.name = name
                    run.url = url
                    run.duration = duration
                    run.cost = cost
                    run.accuracy = accuracy
                    run.input_tokens = input_tokens
                    run.output_tokens = output_tokens
                    timestamp = timestamp

                    # Add the run to the DB
                    db_session.add(run)

            # Commit all the runs
            db_session.commit()


def add_trace(
    trace: Trace,
):
    """
    Add a new trace to the DB.
    """

    with Session(EXPERIMENT_DB_ENGINE) as session:
        session.add(trace)
        session.commit()
        return


def add_run(run: Run):
    """
    Add a new run to the DB.
    """

    with Session(EXPERIMENT_DB_ENGINE) as session:
        session.add(run)
        session.commit()
        return


def update_run(run: Run):
    """
    Update an existing run in the DB.
    """

    with Session(EXPERIMENT_DB_ENGINE) as session:
        session.merge(run)
        session.commit()
        return


def update_run_metrics(run_id: str):
    """
    Update the run with the provided run_id for all calculable metrics, based on the associated traces.
    """
    # TODO continue here
    return


def get_ifc_model(id: int) -> Optional[Ifcmodels]:
    """
    Get the IFC Model from the database from it's id, or None if non is found.
    """
    with Session(EXPERIMENT_DB_ENGINE) as session:
        ifc_model = session.get(Ifcmodels, id)
        return ifc_model


def get_ifc_models() -> List[Ifcmodels]:
    """
    Retrieve all IFC models from the Database
    """
    with Session(EXPERIMENT_DB_ENGINE) as session:
        results = session.exec(select(Ifcmodels))
        ifc_models = [model for model in results]
        return ifc_models


if __name__ == "__main__":
    # dataset = get_dataset(
    #     limit=1,
    #     load_ifc_model=True,
    # )
    # for row in dataset:
    #     print(f"Length of the dataset: {len(dataset)}")
    #     print("QA pair:")
    #     print(row.model_dump_json(indent=2))
    #     print("Related ifc model:")
    #     print(
    #         row.ifc.model_dump_json(indent=2)
    #         if row.ifc is not None
    #         else "No associated IFC models"
    #     )
    #     break
    import_mlflow_experiments()
    import_mlflow_runs()
