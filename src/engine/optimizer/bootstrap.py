import mlflow
from dspy import LM, BootstrapFewShot

from src.config import LANGUAGE_MODELS, OPTIMIZED_MODEL_PATH
from src.engine import IfcAnswerEngine
from src.experiment import TRAINSET, DEVSET, metric

mlflow.dspy.autolog(log_evals=True, log_compiles=True)  # type: ignore
mlflow.set_tracking_uri("http://127.0.0.1:5000")
mlflow.set_experiment(experiment_name="Optimizer")

bootstrap_optimizer = BootstrapFewShot(
    max_bootstrapped_demos=3,
    max_labeled_demos=2**4,
    metric=metric,
    metric_threshold=0.9,
)

teacher_llm = LANGUAGE_MODELS["qwen3-coder"]
teacher_llm = LM(
    model=teacher_llm.url,
    api_key=teacher_llm.api_key,
    max_tokens=2**14,
)
student_llm = LANGUAGE_MODELS["openrouter-gpt-oss-120b"]
student_llm = LM(
    model=student_llm.url,
    api_key=student_llm.api_key,
    max_tokens=2**14,
)
teacher = IfcAnswerEngine(llm=teacher_llm)
student = IfcAnswerEngine(llm=student_llm)

trainset = [qa.to_example() for qa in TRAINSET][:10]

optimized_engine = bootstrap_optimizer.compile(
    student=student,
    teacher=teacher,
    trainset=trainset,
)

optimized_engine.save(OPTIMIZED_MODEL_PATH)
