from datetime import datetime
from typing import List, Optional, cast

import dspy
import mlflow
from tqdm import tqdm

from src.config.agents import AGENT_CONFIGS, EvaluationPipelineConfig
from src.engine import AnswerVerifier, create_engine
from src.engine.schemas import ModuleOutput, OutputsCollection
from src.engine.util import get_logger
from src.experiment.datasets import DEVSET
from src.experiment.db.experiment_models import Dataset


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

        # Create engine using factory function - inherits engine type from IfcAnswerEngine config
        self.engine = create_engine(config=AGENT_CONFIGS.ifc_answer_engine, llm=self.lm)

        # Note: BAML engines don't support load() method like DSPy optimized modules
        if self.config.load_optimized_module and hasattr(self.engine, "load"):
            self.engine.load(path=self.config.path_compiled_model)
        self.answer_verifier = AnswerVerifier()

        # outputs
        self.outputs = OutputsCollection()

    def forward(
        self,
        dataset: List[Dataset] = DEVSET,
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

                # Get the model path from the Dataset relationship
                path_ifc_model = qa_pair.ifc.model_path if qa_pair.ifc else None

                output = cast(
                    ModuleOutput,
                    self.engine(
                        question=qa_pair.question,
                        path_ifc_model=path_ifc_model,
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

                # Garbage collection after each question to prevent resource accumulation
                import gc

                gc.collect()

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
    # Configure multiprocessing to prevent semaphore leaks on macOS
    import multiprocessing as mp

    try:
        mp.set_start_method("fork", force=True)
    except RuntimeError:
        pass

    # Run evaluation with error handling
    mlflow.dspy.autolog(log_evals=True)  # type: ignore
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("ToolOptimizer")

    evaluation = EvaluationPipeline()
    dataset = DEVSET

    # Enable cache?
    dspy.configure_cache(enable_disk_cache=False)

    outputs = cast(
        OutputsCollection,
        evaluation.forward(dataset=dataset),
    )
