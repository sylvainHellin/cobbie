from datetime import datetime
from typing import List, Literal, Optional, cast

import dspy
import mlflow

from src.config.agents import AGENT_CONFIGS, TrainingPipelineConfig
from src.engine import create_engine, TrainingModule
from src.engine.optimizer import bootstrap_engine
from src.engine.schemas import (
    ModuleOutput,
    OutputsCollection,
)
from src.engine.util import get_logger
from src.experiment.datasets import load_train_dev_split
from src.experiment.db.experiment_models import Run, Trace, Dataset
from src.experiment.db.query import add_run, add_trace, update_run_metrics
from src.experiment.evaluation.evaluation import EvaluationPipeline


class TrainingPipeline:
    def __init__(
        self,
        run_id: str,
        experiment_id: str,
        config: Optional[TrainingPipelineConfig] = None,
        lm: Optional[dspy.LM] = None,
    ):
        super().__init__()
        self.run_id = run_id
        self.experiment_id = experiment_id

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

        # Create engine using factory function - inherits engine type from IfcAnswerEngine config
        self.engine = create_engine(
            config=AGENT_CONFIGS.ifc_answer_engine,
            llm=self.lm
        )

        # outputs
        self.outputs = OutputsCollection()

    def _evaluation(
        self,
        mode: Literal["before", "after"],
        devset: List[Dataset],
    ):
        if self.evaluate:
            # Re-initialize the Evaluation Module for each forward pass
            # self.evaluation = EvaluationPipeline()
            self.evaluation.forward(dataset=devset, mode=f"_{mode}_training")
        return

    def _optimize(self):
        if self.config.optimizer == "BootStrapFewShot":
            with mlflow.start_span(name="optimization", span_type="CHAIN") as span:
                self.engine = IfcAnswerEngine(llm=self.lm)
                self.engine = bootstrap_engine(engine=self.engine)
                span.set_status(status="OK")

    def _train(self, trainset: List[Dataset]):
        for qa_pair in trainset:
            with mlflow.start_span(
                name=f"train_question_id_{qa_pair.id}",
                span_type="MODULE",
            ) as trace:
                start = datetime.now()
                output = cast(ModuleOutput, self.training(qa_pair=qa_pair))
                status = "OK" if output.status == "success" else "ERROR"
                duration = (datetime.now() - start).seconds

                trace.set_status(status=status)
                trace.set_inputs(inputs=qa_pair)
                trace.set_outputs(outputs=output)
                self.outputs.add(output=output, update=True)

                tools = "none"
                if output.tools_metrics.nb_tools_updated > 0:
                    mlflow.update_current_trace(tags={"tool merged": "true"})
                    tools = "updated"
                elif output.tools_metrics.nb_tools_created > 0:
                    mlflow.update_current_trace(tags={"tool created": "true"})
                    tools = "created"
                elif output.tools_metrics.nb_tools_merged > 0:
                    mlflow.update_current_trace(tags={"tools merged": "true"})
                    tools = "merged"

                mlflow.update_current_trace(
                    tags={
                        "input tokens": str(output.lm_metrics.input_tokens),
                        "output tokens": str(output.lm_metrics.output_tokens),
                        "accuracy": str(output.result.similarity_score),
                    }
                )

                url = f"http://127.0.0.1:5000/#/experiments/{self.experiment_id}/runs/{self.run_id}/traces:~:text={trace.trace_id}"
                trace_id = trace.trace_id

                # Add trace to the db
                trace = Trace(
                    id=trace_id,
                    run_id=self.run_id,
                    question_id=qa_pair.id,
                    accuracy=output.result.similarity_score,
                    tools=tools,
                    status=status,
                    answer=output.result.answer,
                    duration=duration,
                    llm=output.lm_metrics.llm,
                    timestamp=start,
                    cost=output.lm_metrics.cost,
                    input_tokens=output.lm_metrics.input_tokens,
                    output_tokens=output.lm_metrics.output_tokens,
                    url=url,
                )
                add_trace(trace=trace)

        mlflow.log_metrics(
            metrics={
                "accuracy": self.outputs.mean_acc(),
                "cost": self.outputs.lm_metrics.cost or 0.0,
                "input_tokens": self.outputs.lm_metrics.input_tokens or 0.0,
                "output_tokens": self.outputs.lm_metrics.output_tokens or 0.0,
                "tools_created": self.outputs.tools_metrics.nb_tools_created,
                "tools_updated": self.outputs.tools_metrics.nb_tools_updated,
                "tools_merged": self.outputs.tools_metrics.nb_tools_merged,
            }
        )
        self.logger.info(self.outputs.tools_metrics.model_dump_json(indent=2))
        self.logger.info(self.outputs.lm_metrics.model_dump_json(indent=2))

        update_run_metrics(run_id=self.run_id)

    def forward(
        self,
        devset: List[Dataset],
        trainset: List[Dataset],
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
    run_id: str,
    experiment_id: str,
    trainset: List[Dataset],
    devset: List[Dataset],
):
    # # setup the logger
    # logger = get_logger(
    #     name="Training run", log_level=AGENT_CONFIGS.training_module.log_level
    # )

    training_pipeline = TrainingPipeline(
        run_id=run_id,
        experiment_id=experiment_id,
    )

    # logger.info("Starting the TrainingModule")

    output = training_pipeline.forward(
        devset=devset,
        trainset=trainset,
    )

    return output


if __name__ == "__main__":  # Set-up mlflow
    mlflow.dspy.autolog()  # type: ignore
    mlflow.set_tracking_uri("http://127.0.0.1:5000")

    experiment_name = "Training"
    mlflow.set_experiment(experiment_name)
    experiment = mlflow.get_experiment_by_name(experiment_name)
    experiment_id = str(experiment.experiment_id) if experiment else "0"

    run_name = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    with mlflow.start_run(run_name=run_name) as mlflow_run:
        run_id = mlflow_run.info.run_id
        timestamp = datetime.now()
        db_run = Run(
            id=run_id,
            experiment_id=experiment_id,
            name=run_name,
            timestamp=timestamp,
        )

        # TODO: Continue here
        add_run(run=db_run)
        devset, trainset = load_train_dev_split()
        run_id = mlflow_run.info.run_id
        dspy.configure_cache(
            enable_disk_cache=True,
            enable_memory_cache=True,
        )

        outputs = main(
            experiment_id=experiment_id,
            run_id=run_id,
            devset=[],
            trainset=trainset[:2],
            # devset=devset[:0],
            # trainset=trainset[:2],
        )
