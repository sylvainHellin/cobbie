"""
Agent that ensure QA pairs in the dataset are aligned.
Ensures questions and answers are properly aligned in structure and scope.
"""

import json
import time

import mlflow
from baml_py.baml_py import Collector
from loguru import logger

from src.baml.baml_client import b
from src.db.models import IfcBench
from src.util import setup_logger

setup_logger()


def align_qa_pair(
    qa_pair: IfcBench,
    **kwargs,
) -> IfcBench:
    """
    Align a question-answer pair to ensure structural and semantic alignment.

    Args:
        qa_pair: The IfcBench QA pair to align

    Returns:
        IfcBench: New instance with aligned question and answer (or original if alignment fails)
    """
    # Start timer
    start = time.time()

    # Create collector for capturing the raw prompt
    collector = Collector(name="QAPairAligner")

    with mlflow.start_span(name="QAPairAligner", span_type="LLM") as aligner_span:
        aligner_span.set_inputs(
            {
                "question": qa_pair.question,
                "answer": qa_pair.ground_truth,
                "question_id": qa_pair.id,
                "category": qa_pair.category,
            }
        )

        try:
            # Call BAML alignment function with collector
            aligned_result = b.with_options(
                collector=collector
            ).QuestionAnswerAlignment(
                question=qa_pair.question,
                answer=qa_pair.ground_truth,
                **kwargs,
            )

            # Extract raw prompt from collector
            raw_prompt = None
            try:
                if collector.last and collector.last.calls:
                    first_call = collector.last.calls[0]

                    if hasattr(first_call, "http_request") and first_call.http_request:
                        http_body = first_call.http_request.body

                        # Try text method first
                        if hasattr(http_body, "text"):
                            try:
                                body_text = http_body.text()
                                if body_text:
                                    # Try to parse as JSON to extract messages
                                    try:
                                        body_json = json.loads(body_text)
                                        if (
                                            isinstance(body_json, dict)
                                            and "messages" in body_json
                                        ):
                                            messages = body_json["messages"]
                                            if messages and len(messages) > 0:
                                                # Get the system message content
                                                for msg in messages:
                                                    if msg.get("role") == "system":
                                                        content = msg.get("content", "")
                                                        if (
                                                            isinstance(content, list)
                                                            and len(content) > 0
                                                        ):
                                                            raw_prompt = content[0].get(
                                                                "text", ""
                                                            )
                                                        elif isinstance(content, str):
                                                            raw_prompt = content
                                                        break
                                        else:
                                            # If no messages structure, use the whole text
                                            raw_prompt = body_text
                                    except json.JSONDecodeError:
                                        # If not JSON, use the raw text
                                        raw_prompt = body_text
                            except Exception:
                                pass

                        # Try json method if text didn't work
                        if not raw_prompt and hasattr(http_body, "json"):
                            try:
                                body_json = http_body.json()
                                if (
                                    isinstance(body_json, dict)
                                    and "messages" in body_json
                                ):
                                    messages = body_json["messages"]
                                    if messages and len(messages) > 0:
                                        # Get the system message content
                                        for msg in messages:
                                            if msg.get("role") == "system":
                                                content = msg.get("content", "")
                                                if (
                                                    isinstance(content, list)
                                                    and len(content) > 0
                                                ):
                                                    raw_prompt = content[0].get(
                                                        "text", ""
                                                    )
                                                elif isinstance(content, str):
                                                    raw_prompt = content
                                                break
                                elif isinstance(body_json, str):
                                    raw_prompt = body_json
                            except Exception:
                                pass

                        # Try raw method as last resort
                        if not raw_prompt and hasattr(http_body, "raw"):
                            try:
                                body_raw = http_body.raw()
                                if isinstance(body_raw, bytes):
                                    body_raw = body_raw.decode("utf-8")
                                raw_prompt = body_raw
                            except Exception:
                                pass
            except Exception as e:
                logger.warning(f"Could not extract raw prompt: {e}")

            # Create new IfcBench instance with aligned values
            aligned_qa_pair = IfcBench(
                id=qa_pair.id,
                question=aligned_result.aligned_question,
                ground_truth=aligned_result.aligned_answer,
                ifc_id=qa_pair.ifc_id,
                category=qa_pair.category,
            )

            # Log outputs (including raw prompt)
            aligner_span.set_outputs(
                {
                    "aligned_question": aligned_result.aligned_question,
                    "aligned_answer": aligned_result.aligned_answer,
                    "thought": aligned_result.thought,
                    "raw_prompt": raw_prompt,
                }
            )

            # Calculate metrics
            duration = time.time() - start

            # Log attributes
            aligner_span.set_attributes(
                {
                    "duration": duration,
                    "was_modified": aligned_result.was_modified,
                }
            )

            return aligned_qa_pair

        except Exception as e:
            logger.error(f"Error aligning QA pair {qa_pair.id}: {e}")

            # Log error
            aligner_span.set_outputs(
                {
                    "error": str(e),
                    "returned_original": True,
                }
            )

            # Calculate duration even on error
            duration = time.time() - start
            aligner_span.set_attributes(
                {
                    "duration": duration,
                    "was_modified": False,
                    "error_occurred": True,
                }
            )

            # Return original qa_pair on error
            return qa_pair


if __name__ == "__main__":
    import mlflow

    # Set up MLflow tracking
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("QAPairAligner")

    # Create a test QA pair
    test_qa_pair = IfcBench(
        id=1,
        question="What stair types are used, with their quantities?",
        ground_truth="""Total Stairs: 71

           Stair Types:
           - 24_DD_ betontrap: 32 stairs (45.1%)
           - 24_stair_DD_trapbordes: 18 stairs (25.4%)
           - 24-DD-stalentrap verd: 14 stairs (19.7%)
           - Trap_DD-trap woning type F: 2 stairs (2.8%)
           - Trap_DD-trap woning type G: 2 stairs (2.8%)
           - 24-DD-stalen trap beganegrond: 1 stairs (1.4%)
           - 28_stair_DD_trapbordes: 1 stairs (1.4%)
           - DD-KOOILADDER: 1 stairs (1.4%)

           Concrete Stairs:
           - 24_DD_ betontrap: 32 stairs

           Steel Stairs:
           - 24-DD-stalen trap beganegrond: 1 stairs
           - 24-DD-stalentrap verd: 14 stairs

           Stair Landings:
           - 24_stair_DD_trapbordes: 18 landings
           - 28_stair_DD_trapbordes: 1 landings""",
        ifc_id=1,
        category=1,
    )

    print("Original QA Pair:")
    print(f"Question: {test_qa_pair.question}")
    print(f"Answer: {test_qa_pair.ground_truth}")
    print()

    # Test the alignment function
    aligned_qa_pair = align_qa_pair(test_qa_pair)

    print("Aligned QA Pair:")
    print(f"Question: {aligned_qa_pair.question}")
    print(f"Answer: {aligned_qa_pair.ground_truth}")
    print()

    # Test with already aligned pair
    test_qa_pair_2 = IfcBench(
        id=2,
        question="How many walls are in the building?",
        ground_truth="There are 156 walls in the building.",
        ifc_id=1,
        category=1,
    )

    print("Original QA Pair (Already Aligned):")
    print(f"Question: {test_qa_pair_2.question}")
    print(f"Answer: {test_qa_pair_2.ground_truth}")
    print()

    aligned_qa_pair_2 = align_qa_pair(test_qa_pair_2)

    print("Aligned QA Pair (Should be unchanged):")
    print(f"Question: {aligned_qa_pair_2.question}")
    print(f"Answer: {aligned_qa_pair_2.ground_truth}")
