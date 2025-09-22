from datetime import datetime
from typing import List, Optional, cast

import dspy
import mlflow
from tqdm import tqdm

from src.config.agents import AGENT_CONFIGS, EvaluationPipelineConfig
from src.engine import AnswerVerifier, IfcAnswerEngine
from src.engine.schemas import ModuleOutput, OutputsCollection, QA_Pair
from src.engine.util import get_logger
from src.experiment.datasets import DEVSET


class EvaluationPipeline:
    def __init__(
        self,
        config: Optional[EvaluationPipelineConfig] = None,
        lm: Optional[dspy.LM] = None,
    ):
        super().__init__()
        # Use provided config or default config
        self.config = config or AGENT_CONFIGS.evaluation_pipeline
        self.experiment_name = self.config.experiment_name
        self.start_run = self.config.start_run
        self.logger = get_logger(
            name="EvaluationPipeline", log_level=self.config.log_level
        )

        # Use provided LLM or get from config
        self.lm = lm or self.config.llm.get_llm()

        self.engine = IfcAnswerEngine(llm=self.lm)
        if self.config.load_optimized_module:
            self.engine.load(path=self.config.path_compiled_model)
        self.answer_verifier = AnswerVerifier()

        # outputs
        self.outputs = OutputsCollection()

    def forward(
        self,
        dataset: List[QA_Pair] = DEVSET,
        mode: str = "",
    ) -> OutputsCollection:
        """
        Compute the accuracy of the IfcAnswerEngine.

        Returns:
            OutputsCollection
        """
        self.logger.info(f"Starting evaluation with LLM: {self.lm.model}")

        # Process examples
        for _, qa_pair in enumerate(tqdm(dataset, desc="Evaluating examples")):
            with mlflow.start_span(
                name=f"eval_question_id_{qa_pair.id}",
                span_type="CHAIN",
            ) as span:
                span.set_inputs(inputs=qa_pair.model_dump())

                output = cast(
                    ModuleOutput,
                    self.engine(
                        question=qa_pair.question,
                        path_ifc_model=qa_pair.ifc_model_path,
                    ),
                )
                if output.status == "success":
                    second_output = cast(
                        ModuleOutput,
                        self.answer_verifier(
                            question=qa_pair.question,
                            first_answer=qa_pair.answer,
                            second_answer=output.result.answer,
                        ),
                    )
                    if (
                        second_output.status == "success"
                        and second_output.result.similarity_score is not None
                    ):
                        output.result.similarity_score = (
                            second_output.result.similarity_score
                        )
                        output.combine_lm_metrics(other_output=second_output)
                        self.outputs.add(output=output, update=True)

                span.set_outputs(
                    {
                        "similarity_score": output.result.similarity_score,
                        "answer": output.result.answer,
                    }
                )

                mlflow.update_current_trace(
                    tags={
                        "input tokens": str(output.lm_metrics.input_tokens),
                        "output tokens": str(output.lm_metrics.output_tokens),
                        "similarity score": str(output.result.similarity_score),
                    }
                )

        mlflow.log_metrics(
            {
                f"mean_accuracy{mode}": self.outputs.mean_acc(),
                f"input_tokens{mode}": self.outputs.lm_metrics.input_tokens or 0,
                f"output_tokens{mode}": self.outputs.lm_metrics.output_tokens or 0,
            }
        )
        mlflow.update_current_trace(
            tags={
                "input tokens": str(self.outputs.lm_metrics.input_tokens),
                "output tokens": str(self.outputs.lm_metrics.output_tokens),
                "average accuracy": str(self.outputs.mean_acc()),
            }
        )

        self.logger.info(
            f"Evaluation completed. Mean accuracy: {self.outputs.mean_acc()}"
        )

        return self.outputs


if __name__ == "__main__":
    from src.config.agents import EvaluationPipelineConfig
    from src.config.llm import LLM

    llm = LLM(
        model_name="qwen3-coder",
        provider_name="deepinfra",
    )

    config = EvaluationPipelineConfig(
        load_optimized_module=True,
        llm=llm,
    )

    # setup mlflow
    mlflow.dspy.autolog()  # type: ignore
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("Evaluation")
    mlflow.start_run(run_name=datetime.now().strftime("%Y-%m-%d-%H-%M-%S"))

    evaluation = EvaluationPipeline()
    dataset = DEVSET

    # Enable cache?
    dspy.configure_cache(enable_disk_cache=False)

    outputs = cast(
        OutputsCollection,
        evaluation.forward(dataset=dataset),
    )
