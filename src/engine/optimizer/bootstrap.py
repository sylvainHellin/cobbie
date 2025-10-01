import mlflow
from dspy import BootstrapFewShot

from src.config import LLM_REGISTRY, PATH_COMPILED_MODEL
from src.engine import IfcAnswerEngine
from src.experiment.datasets import TRAINSET
from src.experiment.validation import metric


def bootstrap_engine(
    engine: IfcAnswerEngine = IfcAnswerEngine(),
    save: bool = True,
) -> IfcAnswerEngine:
    # bootstrap_optimizer = BootstrapFewShotWithRandomSearch(
    bootstrap_optimizer = BootstrapFewShot(
        max_bootstrapped_demos=2,
        max_labeled_demos=2**3,
        metric=metric,
        metric_threshold=0.9,
        max_rounds=3,
        max_errors=5,
        # num_threads=1,
        # num_candidate_programs=4,
    )

    teacher_llm = LLM_REGISTRY.create_dspy_llm(
        model_name="qwen3-coder",
        provider_name="deepinfra",
        max_tokens=2**12,
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
    from datetime import datetime

    mlflow.dspy.autolog(log_evals=True, log_compiles=True)  # type: ignore
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment(experiment_name="Optimizer")
    mlflow.start_run(run_name=datetime.now().strftime("%Y-%m-%d-%H-%M-%S"))

    # dspy.configure_cache(
    #     enable_memory_cache=False,
    #     enable_disk_cache=False,
    #     enable_litellm_cache=False,
    # )

    with mlflow.start_span(name="BootstrapFewShort"):
        student_llm = LLM_REGISTRY.create_dspy_llm(
            model_name="qwen3-coder",
            provider_name="deepinfra",
            max_tokens=2**12,
        )

        engine = IfcAnswerEngine(llm=student_llm)

        bootstrap_engine(engine=engine)
