"""
Note: if making any changes in the DB directly, first run:
```zsh
sqlacodegen sqlite:///src/experiment/db/db.db --generator sqlmodels --outfile src/experiment/db/models.py
```
"""

from typing import List

from sqlmodel import Session, col, create_engine, or_, select

from src.config import DB_PATH
from src.experiment.db.models import Dataset, Experiment

url = f"sqlite:///{DB_PATH}"
ENGINE = create_engine(url=url, echo=True)


def get_dataset() -> List[Dataset]:
    """
    Return the whole dataset as a List of Dataset
    """
    with Session(ENGINE) as session:
        statement = select(Dataset).order_by(col(Dataset.id).asc())
        dataset = [row for row in session.exec(statement)]
        return dataset


if __name__ == "__main__":
    experiment = Experiment(
        mlflow_id=str(24),
        mlflow_name="Evaluation",
    )
    with Session(ENGINE) as session:
        # session.add(experiment)
        statement = select(Experiment.mlflow_id).where(
            or_(col(Experiment.id) >= 3),
            Experiment.mlflow_name == "Evaluation",
        )
        results = session.exec(statement).all()

        # datasets
        dataset = get_dataset()
        for row in dataset[:5]:
            print(row.model_dump_json(indent=2))
        session.commit()

GET_DATASET = """-- name: get_dataset \\:many
select id, question, ground_truth, ifc_id
from dataset
order by id asc
"""


GET_EXAMPLE = """-- name: get_example \\:one
select id, question, ground_truth, ifc_id
from dataset
where id = :p1
"""


GET_IFC_MODELS = """-- name: get_ifc_models \\:many
select id, project_name, model_name, model_path, model_description
from ifc_models
"""


INSERT_EXPERIMENT = """-- name: insert_experiment \\:one
INSERT INTO experiment
    (mlflow_name, mlflow_id)
VALUES
    (:p1, :p2)
RETURNING id, mlflow_name, mlflow_id
"""
