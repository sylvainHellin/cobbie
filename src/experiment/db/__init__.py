from sqlmodel import create_engine
from src.config import DB_PATH

EXPERIMENT_DB_ENGINE = create_engine(url=f"sqlite:///{DB_PATH}", echo=True)
MLFLOW_DB_ENGINE = create_engine(url="sqlite:///mlflow.sqlite", echo=True)
