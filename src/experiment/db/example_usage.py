from src.experiment.db.query import Querier
from src.experiment.db.db import get_engine


engine = get_engine()
with engine.connect() as conn:
    querier = Querier(conn=conn)
    dataset = querier.get_dataset()
    for row in dataset:
        print(row)
        break
