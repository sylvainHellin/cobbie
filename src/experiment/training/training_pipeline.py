from datetime import datetime
from typing import List, Literal, Optional, cast

import dspy
import mlflow

from src.config.agents import AGENT_CONFIGS, TrainingPipelineConfig
from src.engine import IfcAnswerEngine, TrainingModule
from src.engine.optimizer import bootstrap_engine
from src.engine.schemas import (
    ModuleOutput,
    OutputsCollection,
    QA_Pair,
)
from src.engine.util import get_logger
from src.experiment.datasets.data_loader import load_train_dev_split
from src.experiment.evaluation.evaluation import EvaluationPipeline


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
        self.evaluation = EvaluationPipeline()

        # Use provided LLM or get from config
        self.lm = lm or self.config.llm.get_llm()
        self.engine = IfcAnswerEngine(llm=self.lm)

        # Set-up mlflow
        mlflow.dspy.autolog()  # type: ignore
        mlflow.set_tracking_uri(self.config.tracking_uri)
        mlflow.set_experiment(self.config.experiment_name)
        mlflow.start_run(run_name=datetime.now().strftime("%Y-%m-%d-%H-%M-%S"))

        # outputs
        self.outputs = OutputsCollection()

    def _evaluation(
        self,
        mode: Literal["before", "after"],
        devset: List[QA_Pair],
    ):
        if self.evaluate:
            # Re-initialize the Evaluation Module for each forward pass
            self.evaluation = EvaluationPipeline()
            self.evaluation.forward(dataset=devset, mode=f"_{mode}_training")
        return

    def _optimize(self):
        if self.config.optimizer == "BootStrapFewShot":
            with mlflow.start_span(name="optimization", span_type="CHAIN") as span:
                self.engine = IfcAnswerEngine(llm=self.lm)
                self.engine = bootstrap_engine(engine=self.engine)
                span.set_status(status="OK")

    def _train(self, trainset: List[QA_Pair]):
        for qa_pair in trainset:
            with mlflow.start_span(
                name=f"train_question_id_{qa_pair.id}",
                span_type="MODULE",
            ) as span:
                output = cast(ModuleOutput, self.training(qa_pair=qa_pair))
                status = "OK" if output.status == "success" else "ERROR"

                span.set_status(status=status)
                span.set_inputs(inputs=qa_pair)
                span.set_outputs(outputs=output)
                self.outputs.add(output=output, update=True)

                if output.tools_metrics.nb_tools_updated > 0:
                    mlflow.update_current_trace(tags={"tool merged": "true"})
                elif output.tools_metrics.nb_tools_created > 0:
                    mlflow.update_current_trace(tags={"tool created": "true"})
                elif output.tools_metrics.nb_tools_merged > 0:
                    mlflow.update_current_trace(tags={"tools merged": "true"})
                mlflow.update_current_trace(
                    tags={
                        "input tokens": str(output.lm_metrics.input_tokens),
                        "output tokens": str(output.lm_metrics.output_tokens),
                        "similarity score": str(output.result.similarity_score),
                    }
                )

        mlflow.log_metrics(
            metrics={
                "mean_acc_training": self.outputs.mean_acc(),
                "training_cost": self.outputs.lm_metrics.cost or 0.0,
                "input_tokens_training": self.outputs.lm_metrics.input_tokens or 0.0,
                "output_tokens_training": self.outputs.lm_metrics.output_tokens or 0.0,
                "tools_created": self.outputs.tools_metrics.nb_tools_created,
                "tools_updated": self.outputs.tools_metrics.nb_tools_updated,
                "tools_merged": self.outputs.tools_metrics.nb_tools_merged,
            }
        )
        self.logger.info(self.outputs.tools_metrics.model_dump_json(indent=2))
        self.logger.info(self.outputs.lm_metrics.model_dump_json(indent=2))

    def forward(
        self,
        devset: List[QA_Pair],
        trainset: List[QA_Pair],
    ) -> OutputsCollection:
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
        devset=devset[: len(devset) // 2],
        trainset=trainset[: len(trainset) // 2],
        #     devset=devset[:2],
        #     trainset=trainset[:2],
    )
