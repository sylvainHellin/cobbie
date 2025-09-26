from src.experiment.db.query import Querier
from src.experiment.db.db import DB_PATH
from sqlalchemy import create_engine


engine = create_engine(url=f"sqlite:///{DB_PATH}")
with engine.connect() as conn:
    querier = Querier(conn=conn)
    dataset = querier.get_dataset()
    for row in dataset:
        print(row)
        break
