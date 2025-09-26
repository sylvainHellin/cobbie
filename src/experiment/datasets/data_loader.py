from typing import List

import pandas as pd

from src.engine.schemas import QA_Pair
from src.experiment.db.db import get_engine
from src.experiment.db.query import Querier

querier = Querier(conn=get_engine().connect())


def load_train_dev_split(
    frac: float = 0.75, seed: int = 42
) -> tuple[List[QA_Pair], List[QA_Pair]]:
    """Load the dataset and split it into a train and dev set."""
    # Load the dataset table from SQLite database
    dataset = querier.get_dataset()
    df_1 = pd.DataFrame([row.model_dump() for row in dataset])
    ifc_models = querier.get_ifc_models()
    df_2 = pd.DataFrame([row.model_dump() for row in ifc_models])
    data = pd.merge(
        left=df_1,
        right=df_2,
        left_on="ifc_id",
        right_on="id",
        suffixes=("", "_ifc"),
    )

    # Split into training and dev sets
    training_df = data.sample(frac=frac, random_state=seed)
    dev_df = data.drop(index=training_df.index.to_list())

    # Convert to dict records and use Pydantic batch validation
    training_records = []
    for idx, row in training_df.iterrows():
        record = {
            "id": row.id,
            "question": row.question,
            "answer": row.ground_truth,
            "project_name": row.project_name,
            "ifc_model_name": row.model_name,
            "ifc_model_path": row.model_path,
            "ifc_model_description": row.model_description,
        }
        training_records.append(record)

    dev_records = []
    for idx, row in dev_df.iterrows():
        record = {
            "id": row.id,
            "question": row.question,
            "answer": row.ground_truth,
            "project_name": row.project_name,
            "ifc_model_name": row.model_name,
            "ifc_model_path": row.model_path,
            "ifc_model_description": row.model_description,
        }
        dev_records.append(record)

    # Batch create Datapoint objects
    training_set = [QA_Pair(**record) for record in training_records]
    dev_set = [QA_Pair(**record) for record in dev_records]

    return training_set, dev_set


TRAINSET, DEVSET = load_train_dev_split()

# Example usage
if __name__ == "__main__":
    sample_datapoint = TRAINSET[0]
    print(f"Question: {sample_datapoint.question}")
    print(f"Question id: {sample_datapoint.id}")
    print(f"Answer: {sample_datapoint.answer}")
    print(f"Project: {sample_datapoint.project_name}")
    print(f"Model: {sample_datapoint.ifc_model_name}")
    print()

    print(f"Training set size: {len(TRAINSET)}")
    print(f"Dev set size: {len(DEVSET)}")
    print("Data loaded successfully!")
