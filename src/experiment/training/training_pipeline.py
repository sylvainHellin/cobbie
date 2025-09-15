from datetime import datetime
from typing import List, Literal, Optional, cast

import dspy
import mlflow

from src.config.agents import AGENT_CONFIGS, TrainingPipelineConfig
from src.engine import IfcAnswerEngine, TrainingModule
from src.engine.optimizer import bootstrap_engine
from src.engine.schemas import (
    ModuleOutput,
    QA_Pair,
    TrainingOutputs,
)
from src.engine.util import get_logger
from src.experiment.datasets.data_loader import load_train_dev_split
from src.experiment.evaluation.evaluation import evaluate


class TrainingPipeline:
    def __init__(
        self,
        config: Optional[TrainingPipelineConfig] = None,
        lm: Optional[dspy.LM] = None,
    ):
        super().__init__()
        # Use provided config or default config
        self.config = config or AGENT_CONFIGS.training_pipeline
        self.logger = get_logger(
            name="TrainingPipeline", log_level=self.config.log_level
        )
        self.evaluate = self.config.evaluate
        self.training = TrainingModule()

        # Use provided LLM or get from config
        self.lm = lm or self.config.llm.get_llm()
        self.engine = IfcAnswerEngine(llm=self.lm)

        # Set-up mlflow
        mlflow.dspy.autolog()  # type: ignore
        mlflow.set_tracking_uri(self.config.tracking_uri)
        mlflow.set_experiment(self.config.experiment_name)
        mlflow.start_run(run_name=datetime.now().strftime("%Y-%m-%d-%H-%M-%S"))

        # outputs
        self.outputs = TrainingOutputs()

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
                    engine=self.engine,
                )
                metrics = {
                    f"mean_accuracy_{mode}_training": eval.mean_accuracy(),
                    f"nb_errors_{mode}_training": float(eval.total_errors()),
                    f"mean_duration_{mode}_training": eval.mean_duration(),
                    f"input_tokens_{mode}_training": float(eval.total_input_tokens()),
                    f"output_tokens_{mode}_training": float(eval.total_output_tokens()),
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

    def _optimize(self):
        if self.config.optimizer == "BootStrapFewShot":
            with mlflow.start_span(name="optimization", span_type="CHAIN") as span:
                self.engine = IfcAnswerEngine(llm=self.lm)
                self.engine = bootstrap_engine(engine=self.engine)
                span.set_status(status="OK")

    def _train(self, trainset: List[QA_Pair]):
        for qa_pair in trainset:
            outputs = cast(ModuleOutput, self.training(qa_pair=qa_pair))
            self.outputs.add(output=outputs, update=True)

        # mlflow.log_metrics(metrics=self.outputs.tools_metrics.model_dump())
        # mlflow.log_metrics(metrics=self.outputs.lm_metrics.model_dump())
        self.logger.info(self.outputs.tools_metrics.model_dump_json(indent=2))
        self.logger.info(self.outputs.lm_metrics.model_dump_json(indent=2))

    def forward(
        self,
        devset: List[QA_Pair],
        trainset: List[QA_Pair],
    ) -> TrainingOutputs:
        """Process QA pairs from a training set to train the engine to create, update and merge tools. Will also perform evaluation and optimization if set up in the config."""

        # Evaluate the accuracy of the engine before the training round (if setup in the config)
        self._evaluation(
            mode="before",
            devset=devset,
        )

        # Train the module
        self._train(trainset=trainset)

        # Compile the program before the final evaluation
        self._optimize()

        # Evaluate the accuracy of the engine after the training round.
        self._evaluation(
            mode="after",
            devset=devset,
        )

        return self.outputs


def main(
    trainset: List[QA_Pair],
    devset: List[QA_Pair],
):
    # # setup the logger
    # logger = get_logger(
    #     name="Training run", log_level=AGENT_CONFIGS.training_module.log_level
    # )

    training_pipeline = TrainingPipeline()

    # logger.info("Starting the TrainingModule")

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
        devset=devset[:3],
        trainset=trainset[:3],
    )
