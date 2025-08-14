from datetime import datetime
from time import time
from typing import List, Optional, cast

import mlflow
from dspy import LM
from tqdm import tqdm

from src.engine import IfcAnswerEngine
from src.engine.schemas import EvaluationResult, QA_Pair, ModuleOutput
from src.engine.util import get_logger
from src.experiment.datasets import DEVSET
from src.experiment.validation import metric


def evaluate(
    llm: LM,
    dataset: List[QA_Pair] = DEVSET,
    experiment_name: Optional[str] = "Evaluation",
    start_run: bool = False,
    log_metris: bool = False,
    engine: Optional[IfcAnswerEngine] = None,
) -> EvaluationResult:
    """
    Compute the accuracy of the IfcAnswerEngine.

    Returns:
        ValidationResult: Comprehensive evaluation results with error tracking
    """
    logger = get_logger("Evaluation")
    logger.info(f"Starting evaluation with LLM: {llm.model}")

    # Setup mlflow
    if experiment_name is not None:
        mlflow.set_experiment(experiment_name=experiment_name)
        logger.info(f"MLflow experiment set: {experiment_name}")
    if start_run:
        mlflow.start_run(run_name=datetime.now().strftime("%Y-%m-%d-%H-%M-%S"))
        logger.info("New run started.")

    # Initialize result
    result = EvaluationResult(llm=llm.model)

    # Initialize engine with provided LLM so compiled few-shot engine uses same model
    if engine is None:
        engine = IfcAnswerEngine(llm=llm)

    # Process examples
    for _, qa_pair in enumerate(tqdm(dataset, desc="Evaluating examples")):
        with mlflow.start_span(
            name=f"question_id_{qa_pair.id}",
            span_type="CHAIN",
        ):
            # Increment total evaluation count
            result.increment_eval_count()

            # Execute engine
            start = time()
            engine_output = cast(
                ModuleOutput,
                engine(
                    question=qa_pair.question,
                    path_ifc_model=qa_pair.ifc_model_path,
                ),
            )
            end = time()
            duration = end - start

            # Record metrics
            result.duration.append(duration)
            result.tokens.append(
                (engine_output.input_tokens or 0, engine_output.output_tokens or 0)
            )
            result.question_ids.append(qa_pair.id)
            result.cost.append(engine_output.cost or 0)

            if engine_output.status == "error":
                result.add_error(
                    qa_pair.id,
                    engine_output.error_msg or "",
                )
                continue

            acc = metric(example=qa_pair.to_example(), output=engine_output)
            result.accuracy.append(acc)

    # Log final summary
    successful_evaluations = result.nb_eval - result.nb_failed_eval
    logger.info(
        f"Evaluation completed: {successful_evaluations} successful, {result.nb_failed_eval} failed out of {result.nb_eval} total"
    )
    logger.info(f"Success rate: {result.evaluation_success_rate():.2%}")
    logger.info(f"Mean accuracy: {result.mean_accuracy():.3f}")
    logger.info(f"Mean duration: {result.mean_duration():.2f}s")
    logger.info(f"Total tokens: {result.total_tokens():,}")

    if result.errors:
        logger.warning(f"Total errors encountered: {len(result.errors)}")

    # Log metrics to MLflow if a run is active
    if mlflow.active_run() is not None and log_metris:
        mlflow.log_metrics(
            metrics={
                "mean_accuracy": result.mean_accuracy(),
                "nb_errors": float(len(result.errors)),
                "mean_duration": result.mean_duration(),
                "cost": result.total_cost(),
            },
        )
        logger.info("Logged metrics to MLflow.")

    return result


if __name__ == "__main__":
    # Run evaluation with error handling
    from src.config import LLM

    llm = LLM(
        model_name="gpt-oss-120b",
        provider_name="openrouter",
    ).get_llm()

    mlflow.dspy.autolog(log_evals=True)  # type: ignore
    mlflow.set_tracking_uri("http://127.0.0.1:5000")

    result = evaluate(
        llm=llm,
        start_run=True,
        dataset=DEVSET[12:14],
        log_metris=True,
    )

    # Check your tracking attributes
    print(f"Total attempts: {result.nb_eval}")
    print(f"Failed attempts: {result.nb_failed_eval}")
    print(f"Success rate: {result.evaluation_success_rate():.2%}")
