from datetime import datetime
from typing import List, Literal, Optional, Tuple

import dspy
import mlflow

from src.config import AGENT_CONFIGS
from src.engine.components.training_module import (
    TrainingModule,
)
from src.engine.schemas import (
    ModuleOutput,
    QA_Pair,
    ToolsMetrics,
)
from src.engine.util import get_logger, get_usage_openrouter
from src.experiment.evaluation.evaluation import evaluate
from src.experiment.datasets import load_train_dev_split


class TrainingPipeline(dspy.Module):
    def __init__(
        self,
        config=None,
        lm: Optional[dspy.LM] = None,
    ):
        super().__init__()
        # Use provided config or default config
        self.config = config or AGENT_CONFIGS.training_pipeline
        self.logger = get_logger(name="Training", log_level=self.config.log_level)
        self.evaluate = self.config.evaluate
        self.training = TrainingModule()
        self.current_api_usage = get_usage_openrouter()

        # Use provided LLM or get from config
        self.lm = lm or self.config.llm.get_llm()

        # Set-up mlflow
        mlflow.dspy.autolog()  # type: ignore
        mlflow.set_tracking_uri(self.config.tracking_uri)
        mlflow.set_experiment(self.config.experiment_name)
        mlflow.start_run(run_name=datetime.now().strftime("%Y-%m-%d-%H-%M-%S"))

        # outputs
        self.outputs: List[ModuleOutput] = []
        self.tools_metrics = ToolsMetrics()

    def _evaluation(
        self,
        mode: Literal["before", "after"],
        devset: List[QA_Pair],
    ):
        if self.evaluate:
            with mlflow.start_span(
                name=f"evaluation_{mode}",
                span_type="CHAIN",
            ) as span:
                # run eval
                eval = evaluate(
                    llm=self.lm,
                    start_run=False,
                    dataset=devset,
                )
                metrics = {
                    f"mean_accuracy_{mode}_training": eval.mean_accuracy(),
                    f"nb_errors_{mode}_training": len(eval.errors),
                    f"mean_duration_{mode}_training": eval.mean_duration(),
                    f"input_tokens_{mode}_training": eval.total_input_tokens(),
                    f"output_tokens_{mode}_training": eval.total_output_tokens(),
                    f"cost_{mode}_training": eval.total_cost(),
                }
                span.set_attributes(attributes=metrics)

                # Convert metrics to str for tags
                mlflow.update_current_trace(
                    tags={k: str(v) for k, v in metrics.items()}
                )
            # Log the metrics
            mlflow.log_metrics(
                metrics=metrics,
            )
            mlflow.log_param(key="model", value=self.lm.model)

        return

    def forward(
        self,
        devset: List[QA_Pair],
        trainset: List[QA_Pair],
    ) -> Tuple[List[ModuleOutput], ToolsMetrics]:
        """Process QA pairs from a training set to train the engine to create, update and merge tools. Will also perform evaluation and optimization if set up in the config."""

        # Evaluate the accuracy of the engine before the training round (if setup in the config)
        self._evaluation(
            mode="before",
            devset=devset,
        )
        initial_usage = get_usage_openrouter()

        # Go through each examples in the training set
        for qa_pair in trainset:
            output, metrics = self.training.forward(qa_pair=qa_pair)
            self.tools_metrics.update(metrics=metrics)
            self.outputs.append(output)

            # add the output to the final outputs
            self.outputs.append(output)

        self.tools_metrics.cost = get_usage_openrouter() - initial_usage
        mlflow.log_metrics(metrics=self.tools_metrics.model_dump())

        # Evaluate the accuracy of the engine after the training round.
        self._evaluation(mode="after", devset=devset)

        return (self.outputs, self.tools_metrics)


def main(
    trainset: List[QA_Pair],
    devset: List[QA_Pair],
):
    # setup the logger
    logger = get_logger(
        name="Training run", log_level=AGENT_CONFIGS.training_module.log_level
    )

    training_pipeline = TrainingPipeline()

    logger.info("Starting the TrainingModule")

    output = training_pipeline.forward(
        devset=devset,
        trainset=trainset,
    )

    return output


if __name__ == "__main__":
    devset, trainset = load_train_dev_split()
    dspy.configure_cache(
        enable_disk_cache=True,
        enable_memory_cache=True,
    )

    outputs = main(
        devset=devset[7:15],
        trainset=trainset[7:15],
    )
