import mlflow
from dspy import LabeledFewShot

from src.config import OPTIMIZED_MODEL_PATH
from src.engine import IfcAnswerEngine
from src.experiment import TRAINSET


def add_fewshot_examples(
    engine: IfcAnswerEngine,
    save: bool = False,
    k: int = 2**4,
) -> IfcAnswerEngine:
    fewshot = LabeledFewShot(k=k)

    trainset = [qa.to_example() for qa in TRAINSET][:]
    optimized_engine = fewshot.compile(
        student=engine,
        trainset=trainset,
    )
    if save:
        optimized_engine.save(path=OPTIMIZED_MODEL_PATH)

    return optimized_engine


if __name__ == "__main__":
    mlflow.dspy.autolog(log_evals=True, log_compiles=True)  # type: ignore
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment(experiment_name="Optimizer")

    engine = IfcAnswerEngine()
    add_fewshot_examples(engine=engine, save=True)
