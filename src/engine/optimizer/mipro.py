from typing import List

import mlflow
from dspy import MIPROv2

from src.config import PATH_COMPILED_MODEL
from src.engine import IfcAnswerEngine
from src.engine.schemas import QA_Pair
from src.experiment import TRAINSET, metric

optimizer = MIPROv2(
    metric=metric,
    auto=None,
    num_candidates=3,
)


def mipro_engine_optimizer(
    dataset: List[QA_Pair],
    engine: IfcAnswerEngine,
    save: bool = True,
) -> IfcAnswerEngine:
    trainset = [qa.to_example() for qa in dataset]
    optimized_engine = optimizer.compile(
        num_trials=7,
        student=engine,
        trainset=trainset,
    )
    if save:
        optimized_engine.save(PATH_COMPILED_MODEL)

    return optimized_engine


if __name__ == "__main__":
    mlflow.dspy.autolog(log_evals=True, log_compiles=True)  # type: ignore
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment(experiment_name="Optimizer")

    # Using the new LLM configuration system
    from src.config.llm import LLM

    # Create LLM config - you can specify both model and provider
    llm_config = LLM(
        model_name="qwen3-coder",
        provider_name="openrouter",  # or "ollama" for free usage
        max_tokens=2**14,
    )

    # Get the dspy.LM instance
    llm = llm_config.get_llm()

    with mlflow.start_run(run_name="MiproV2") as run:
        engine = IfcAnswerEngine()

        if engine.config.load_optimized_module:
            engine.load(path=PATH_COMPILED_MODEL)

        mipro_engine_optimizer(
            dataset=TRAINSET,
            engine=engine,
        )
