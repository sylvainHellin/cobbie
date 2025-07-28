from src.experiment.db import connection
from src.engine.schemas import QA_Pair
import pandas as pd
from typing import List


def load_train_dev_split(
    frac: float = 0.75, seed: int = 42
) -> tuple[List[QA_Pair], List[QA_Pair]]:
    """Load the dataset and split it into a train and dev set."""
    # Load the dataset table from SQLite database
    dataset = pd.read_sql("SELECT * FROM dataset ORDER BY id ASC", connection())
    dataset.set_index("id", inplace=True)
    ifc_models = pd.read_sql("SELECT * FROM ifc_models", connection())
    dataset = pd.merge(
        left=dataset,
        right=ifc_models,
        left_on="ifc_id",
        right_on="id",
        suffixes=("", "_ifc"),
    )

    # Split into training and dev sets
    training_df = dataset.sample(frac=frac, random_state=seed)
    dev_df = dataset.drop(index=training_df.index.to_list())

    # Convert to dict records and use Pydantic batch validation
    training_records = []
    for idx, row in training_df.iterrows():
        record = {
            "id": idx,  # idx is the original dataset.id (question id)
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
            "id": idx,  # idx is the original dataset.id (question id)
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


# Example usage - much cleaner access to fields
if __name__ == "__main__":
    TRAINING_SET, DEV_SET = load_train_dev_split()
    sample_datapoint = TRAINING_SET[0]
    print(f"Question: {sample_datapoint.question}")
    print(f"Question id: {sample_datapoint.id}")
    print(f"Answer: {sample_datapoint.answer}")
    print(f"Project: {sample_datapoint.project_name}")
    print(f"Model: {sample_datapoint.ifc_model_name}")
    print()

    print(f"Training set size: {len(TRAINING_SET)}")
    print(f"Dev set size: {len(DEV_SET)}")
    print("Data loaded successfully!")
