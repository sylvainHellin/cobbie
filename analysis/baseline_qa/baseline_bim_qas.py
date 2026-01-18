"""
Baseline BIM-QA System.

Answers BIM questions using a static model summary approach.
No dynamic retrieval - just a one-time summary passed to the LLM.
"""

import time
from contextlib import nullcontext
from typing import Optional, Tuple

import mlflow
from baml_py import baml_py
from baml_py.baml_py import Collector
from loguru import logger

from analysis.baseline_qa.ifc_summary import get_or_create_summary
from baml_client import b
from baml_client.types import FinalAnswer


def baseline_bim_qas(
    user_input: str,
    model_path: str,
    client: str = "GLM_4_7",
    mlflow_run_id: Optional[str] = None,
    **kwargs,
) -> Tuple[FinalAnswer, Collector, str]:
    """
    Answer a BIM question using static model summary approach.

    This is the baseline system for comparison with COBBIE. It extracts a one-time
    summary from the IFC model and passes it as context to the LLM for each question.
    No tools or dynamic retrieval are used.

    Args:
        user_input: The question to answer
        model_path: Path to the IFC model file
        client: BAML client name to use (default: GLM_4_7)
        mlflow_run_id: Optional MLflow run ID to use
        **kwargs: Additional arguments (ignored for baseline)

    Returns:
        Tuple of (FinalAnswer, Collector, conversation_history)
        - FinalAnswer contains the answer and reasoning
        - Collector tracks token usage
        - conversation_history is a simple log of the interaction
    """
    logger.info(f"[BASELINE] Answering question: {user_input[:100]}...")

    # Create collector for token tracking
    collector = Collector(name="BaselineQA")

    # Create client registry to override default BAML client
    client_registry = baml_py.ClientRegistry()
    client_registry.set_primary(client)

    # Get or create cached summary for the model
    model_summary = get_or_create_summary(model_path)

    # Build conversation history log
    history_lines = [
        "=== BASELINE QA SYSTEM ===",
        f"Question: {user_input}",
        f"Model: {model_path}",
        f"Summary length: {len(model_summary)} chars (~{len(model_summary)//4} tokens)",
        "",
    ]

    # Check if we're already in an MLflow run, or if a run_id was provided
    active_run = mlflow.active_run()

    if mlflow_run_id:
        run_context_manager = mlflow.start_run(run_id=mlflow_run_id)
    elif active_run:
        run_context_manager = nullcontext()
    else:
        run_context_manager = mlflow.start_run(run_name="BaselineQA")

    with run_context_manager:
        # Log parameters if we created a new run
        if not active_run and not mlflow_run_id:
            mlflow.log_params(
                {
                    "component": "BaselineQA",
                    "model_path": model_path,
                    "client": client,
                    "summary_length_chars": len(model_summary),
                    "system": "baseline",
                }
            )

        # Start MLflow span for the LLM call
        with mlflow.start_span(name="BaselineQA", span_type="LLM") as span:
            span.set_inputs(
                {
                    "user_input": user_input,
                    "model_path": model_path,
                    "model_summary": model_summary,  # Full summary for debugging
                    "summary_length": len(model_summary),
                }
            )

            start_time = time.time()

            try:
                # Call BAML function with summary context
                final_answer = b.BaselineQA(
                    user_input=user_input,
                    model_summary=model_summary,
                    baml_options={
                        "collector": collector,
                        "client_registry": client_registry,
                    },
                )
            except Exception as e:
                # Handle errors gracefully - return ERROR answer like Cobbie does
                logger.error(f"[BASELINE] Error during BAML call: {e}")
                execution_time = time.time() - start_time

                final_answer = FinalAnswer(
                    answer="ERROR",
                    thoughts=f"Baseline QA failed with exception: {e}",
                )

                # Log failure metrics
                mlflow.log_metrics(
                    {
                        "baseline_input_tokens": 0,
                        "baseline_output_tokens": 0,
                        "baseline_total_tokens": 0,
                        "baseline_execution_time": execution_time,
                        "baseline_success": 0,
                    }
                )

                span.set_outputs(
                    {
                        "error": str(e),
                        "execution_time": execution_time,
                    }
                )
                span.set_status("ERROR")

                history_lines.extend(
                    [
                        "=== ERROR ===",
                        f"Exception: {e}",
                        f"Execution time: {execution_time:.2f}s",
                    ]
                )

                conversation_history = "\n".join(history_lines)
                return final_answer, collector, conversation_history

            execution_time = time.time() - start_time

            # Extract token usage from collector
            input_tokens = 0
            output_tokens = 0
            total_tokens = 0

            if collector and hasattr(collector, "usage") and collector.usage:
                usage = collector.usage
                input_tokens = usage.input_tokens or 0
                output_tokens = usage.output_tokens or 0
                total_tokens = input_tokens + output_tokens

            # Log metrics
            mlflow.log_metrics(
                {
                    "baseline_input_tokens": input_tokens,
                    "baseline_output_tokens": output_tokens,
                    "baseline_total_tokens": total_tokens,
                    "baseline_execution_time": execution_time,
                    "baseline_success": 1,
                }
            )

            # Set span outputs
            span.set_outputs(
                {
                    "answer": final_answer.answer,
                    "reasoning": final_answer.thoughts,
                    "execution_time": execution_time,
                }
            )

            span.set_attributes(
                {
                    "token_usage.input_tokens": input_tokens,
                    "token_usage.output_tokens": output_tokens,
                    "token_usage.total_tokens": total_tokens,
                    "llm.client": client,
                }
            )

            logger.info(
                f"[BASELINE] Tokens used: {total_tokens} -- Latency: {execution_time:.2f}s"
            )

            # Complete history log
            history_lines.extend(
                [
                    "=== LLM RESPONSE ===",
                    f"Thoughts: {final_answer.thoughts}",
                    f"Answer: {final_answer.answer}",
                    "",
                    f"Execution time: {execution_time:.2f}s",
                    f"Tokens: {total_tokens} (in: {input_tokens}, out: {output_tokens})",
                ]
            )

            conversation_history = "\n".join(history_lines)

            return final_answer, collector, conversation_history


if __name__ == "__main__":
    # Test the baseline system
    import mlflow

    from src.config import TEST_IFC_PATH

    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("BaselineQA_Test")

    test_question = "How many walls are there in the BIM model?"

    print("BASELINE QA Test Execution:")
    print(f"Question: {test_question}")
    print(f"Model Path: {TEST_IFC_PATH}\n")

    result, collector, history = baseline_bim_qas(
        user_input=test_question,
        model_path=TEST_IFC_PATH,
        client="GLM_4_7",
    )

    print("\nBaseline QA Results:")
    print(f"Answer: {result.answer}")
    print(f"Reasoning: {result.thoughts}")
    print("\n--- Conversation History ---")
    print(history)
