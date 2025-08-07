from dspy import BootstrapFewShotWithRandomSearch, LM
import mlflow
from src.experiment import metric, evaluate, TRAINSET, DEVSET
from src.engine import IfcAnswerEngine
from src.config import OPTIMIZED_MODEL_PATH, LANGUAGE_MODELS

mlflow.dspy.autolog(log_evals=True, log_compiles=True)  # type: ignore
mlflow.set_tracking_uri("http://127.0.0.1:5000")
mlflow.set_experiment(experiment_name="Optimizer")

optimizer = BootstrapFewShotWithRandomSearch(
    max_bootstrapped_demos=4,
    max_labeled_demos=4,
    num_candidate_programs=10,
    num_threads=2,
    metric=metric,
)
llm = LANGUAGE_MODELS["qwen3-coder"]
llm = LM(
    model=llm.url,
    api_key=llm.api_key,
    max_tokens=2**14,
)
# res_1 = evaluate(llm=llm)
engine = IfcAnswerEngine()

trainset = [qa.to_example() for qa in TRAINSET][:10]
optimized_engine = optimizer.compile(
    student=engine,
    trainset=trainset,
)

optimized_engine.save(OPTIMIZED_MODEL_PATH)
