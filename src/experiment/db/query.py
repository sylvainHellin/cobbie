"""
Note: if making any changes in the DB directly, first run:
```zsh
sqlacodegen sqlite:///src/experiment/db/db.db --generator sqlmodels --outfile src/experiment/db/experiment_models.py
sqlacodegen sqlite:///mlflow.sqlite --generator sqlmodels --outfile src/experiment/db/mlflow_models.py
```
"""

from functools import wraps
from typing import Callable, List, TypeVar, Optional

from sqlmodel import Session, col, or_, select
from sqlalchemy.orm import selectinload

from src.experiment.db import EXPERIMENT_DB_ENGINE, MLFLOW_DB_ENGINE
from src.experiment.db.experiment_models import Dataset, Experiment, Ifcmodels
from src.experiment.db.mlflow_models import Experiments

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


def mirror_experiment_mlflow():
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
    mirror_experiment_mlflow()
