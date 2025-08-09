import mlflow
from dspy import LM, BootstrapFewShotWithRandomSearch

from src.config import LANGUAGE_MODELS, OPTIMIZED_MODEL_PATH
from src.engine import IfcAnswerEngine
from src.experiment import TRAINSET, metric

mlflow.dspy.autolog(log_evals=True, log_compiles=True)  # type: ignore
mlflow.set_tracking_uri("http://127.0.0.1:5000")
mlflow.set_experiment(experiment_name="Optimizer")

bootstrap_optimizer = BootstrapFewShotWithRandomSearch(
    max_bootstrapped_demos=4,
    max_labeled_demos=4,
    num_candidate_programs=10,
    num_threads=2,
    metric=metric,
)
# llm = LANGUAGE_MODELS["devstral-medium"]
llm = LANGUAGE_MODELS["qwen3-coder"]
llm = LM(
    model=llm.url,
    api_key=llm.api_key,
    max_tokens=2**14,
)

engine = IfcAnswerEngine()

trainset = [qa.to_example() for qa in TRAINSET][:]
optimized_engine = bootstrap_optimizer.compile(
    student=engine,
    trainset=trainset,
)

optimized_engine.save(OPTIMIZED_MODEL_PATH)
