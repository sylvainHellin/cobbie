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
from src.engine.util import (
    get_logger,
)
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
                name="start_evaluation",
                span_type="CHAIN",
            ):
                # run eval
                eval = evaluate(
                    llm=self.lm,
                    start_run=False,
                    dataset=devset,
                )
            # Log the metrics
            mlflow.log_metrics(
                metrics={
                    f"mean_accuracy_{mode}_training": eval.mean_accuracy(),
                    f"nb_errors_{mode}_training": len(eval.errors),
                    f"mean_duration_{mode}_training": eval.mean_duration(),
                },
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

        # Go through each examples in the training set
        for qa_pair in trainset:
            with mlflow.start_span(
                name=f"question_id_{qa_pair.id}",
                span_type="QUESTION",
            ) as span:
                span.set_attribute("question_id", qa_pair.id)
                span.set_attribute("question", qa_pair.question)
                span.set_attribute("ground_truth", qa_pair.answer)

                output, metrics = self.training.forward(qa_pair=qa_pair)
                self.tools_metrics.update(metrics=metrics)
                self.outputs.append(output)

                # add the output to the final outputs
                self.outputs.append(output)

        # Evaluate the accuracy of the engine after the training round.
        self._evaluation(mode="after", devset=devset)
        mlflow.log_metrics(metrics=self.tools_metrics.model_dump())

        return (self.outputs, self.tools_metrics)


def main(
    trainset: List[QA_Pair],
    devset: List[QA_Pair],
):
    # setup the logger
    logger = get_logger(
        name="Training run", log_level=AGENT_CONFIGS.training_module.log_level
    )

    training_module = TrainingPipeline()

    logger.info("Starting the TrainingModule")

    output = training_module.forward(
        devset=devset,
        trainset=trainset,
    )

    return output


if __name__ == "__main__":
    devset, trainset = load_train_dev_split()

    outputs = main(
        devset=devset[:10],
        trainset=trainset[:10],
    )
