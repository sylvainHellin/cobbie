import mlflow
from dspy import LM, BootstrapFewShot, BootstrapFewShotWithRandomSearch

from src.config import LANGUAGE_MODELS, PATH_COMPILED_MODEL
from src.engine import IfcAnswerEngine
from src.experiment import TRAINSET, metric


def bootstrap_engine(
    engine: IfcAnswerEngine = IfcAnswerEngine(),
    save: bool = True,
) -> IfcAnswerEngine:
    bootstrap_optimizer = BootstrapFewShotWithRandomSearch(
        max_bootstrapped_demos=3,
        max_labeled_demos=2**4,
        metric=metric,
        metric_threshold=0.9,
        max_rounds=3,
        max_errors=5,
        num_threads=1,
        num_candidate_programs=4,
    )

    teacher_llm = LANGUAGE_MODELS["openrouter-claude"]
    teacher_llm = LM(
        model=teacher_llm.url,
        api_key=teacher_llm.api_key,
        max_tokens=2**14,
    )

    teacher = IfcAnswerEngine(llm=teacher_llm)
    trainset = [qa.to_example() for qa in TRAINSET]

    optimized_engine = bootstrap_optimizer.compile(
        student=engine,
        teacher=teacher,
        trainset=trainset,
    )

    if save:
        optimized_engine.save(PATH_COMPILED_MODEL)

    return optimized_engine


if __name__ == "__main__":
    mlflow.dspy.autolog(log_evals=True, log_compiles=True)  # type: ignore
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment(experiment_name="Optimizer")

    with mlflow.start_span(name="BootstrapFewShort"):
        student_llm = LANGUAGE_MODELS["openrouter-gpt-oss-120b"]
        student_llm = LM(
            model=student_llm.url,
            api_key=student_llm.api_key,
            max_tokens=2**14,
        )
        engine = IfcAnswerEngine(llm=student_llm)

        bootstrap_engine(engine=engine)
