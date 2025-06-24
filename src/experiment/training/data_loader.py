from src.config import DATASET_PATH
import pandas as pd

dataset = pd.read_csv(filepath_or_buffer=DATASET_PATH)
training_set = dataset.sample(frac=0.75, random_state=42)
dev_set = dataset.drop(index=training_set.index.to_list())

TRAINING_SET_LOADER = training_set.itertuples(name="train")
DEV_SET_LOADER = dev_set.itertuples(name="dev")


for row in TRAINING_SET_LOADER:
    print(row.question)  # type: ignore
    print(row.answer)  # type: ignore
    print()
    break
print("END")
