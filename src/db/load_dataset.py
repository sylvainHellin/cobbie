
import csv
import os
from typing import List, Tuple

from src.db.query import get_dataset, get_ifc_models

from src.db.models import IfcBench

# The evaluation split is a frozen experiment artifact, not part of the dataset
# identity. It is pinned by question id in this checked-in file (columns
# id,split) so the held-out test set is reproducible and seed-free.
FROZEN_SPLIT_PATH = os.path.join(os.path.dirname(__file__), "frozen_split.csv")


def _load_test_ids(path: str = FROZEN_SPLIT_PATH) -> set[int]:
    """Return the set of question ids marked ``test`` in the frozen split file."""
    test_ids: set[int] = set()
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if row["split"].strip() == "test":
                test_ids.add(int(row["id"]))
    return test_ids


def load_train_test_split() -> Tuple[List[IfcBench], List[IfcBench]]:
    """Load the dataset and split it into a train and held-out test set.

    The split is read from the frozen split file (``frozen_split.csv``): each db
    row is assigned to the test set if its ``id`` is in the frozen test-id set,
    otherwise to the train set. This is order-independent and seed-free.
    """
    # Load the dataset table from SQLite database
    dataset = get_dataset()
    ifc_models = get_ifc_models()

    # Create a mapping of ifc_id to ifc model objects for efficient lookup
    ifc_model_map = {model.id: model for model in ifc_models}

    # Populate the ifc relationship for each dataset entry
    for data in dataset:
        data.ifc = ifc_model_map.get(data.ifc_id)

    # Partition by matching each db row's id against the frozen test-id set.
    test_ids = _load_test_ids()
    train_data = [data for data in dataset if data.id not in test_ids]
    test_data = [data for data in dataset if data.id in test_ids]

    return train_data, test_data


# Load the datasets
TRAINSET, TESTSET = load_train_test_split()

__all__ = [
    "load_train_test_split",
    "TRAINSET",
    "TESTSET",
]
