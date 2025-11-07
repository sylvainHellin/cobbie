
from typing import List, Tuple
from src.db.query import get_dataset, get_ifc_models
import random

from src.db.models import IfcBench

def load_train_dev_split(
    frac: float = 0.75, seed: int = 42
) -> Tuple[List[IfcBench], List[IfcBench]]:
    """Load the dataset and split it into a train and dev set."""
    # Load the dataset table from SQLite database
    dataset = get_dataset()
    ifc_models = get_ifc_models()

    # Create a mapping of ifc_id to ifc model objects for efficient lookup
    ifc_model_map = {model.id: model for model in ifc_models}

    # Populate the ifc relationship for each dataset entry
    for data in dataset:
        data.ifc = ifc_model_map.get(data.ifc_id)

    # Split into training and dev sets
    total_items = len(dataset)
    train_size = int(total_items * frac)

    # Shuffle the dataset using the provided seed for reproducible randomization
    random.seed(seed)
    shuffled_dataset = dataset.copy()
    random.shuffle(shuffled_dataset)

    # Split the shuffled dataset
    train_data = shuffled_dataset[:train_size]
    dev_data = shuffled_dataset[train_size:]

    return train_data, dev_data


# Load the datasets
TRAINSET, DEVSET = load_train_dev_split()

__all__ = [
    "load_train_dev_split",
    "TRAINSET",
    "DEVSET",
]
