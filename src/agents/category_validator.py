"""
Agent that validate the categories for QA pairs in the dataset.
Validates that questions are correctly categorized according to the 4-category taxonomy.
"""

import json
import time

import mlflow
from baml_py.baml_py import Collector

from baml_client import b
from src.db.models import IfcBench


def validate_category(
    qa_pair: IfcBench,
    **kwargs,
) -> IfcBench:
    """
    Validate the category of a question-answer pair according to the 4-category taxonomy.

    Args:
        qa_pair: The IfcBench QA pair to validate

    Returns:
        IfcBench: New instance with validated category (or original category if validation fails)
    """
    # Start timer
    start = time.time()

    # Create collector for capturing the raw prompt
    collector = Collector(name="CategoryValidator")

    with mlflow.start_span(name="CategoryValidator", span_type="LLM") as validator_span:
        validator_span.set_inputs(
            {
                "question": qa_pair.question,
                "answer": qa_pair.ground_truth,
                "question_id": qa_pair.id,
                "current_category": qa_pair.category,
            }
        )

        try:
            # Call BAML validation function with collector
            validation_result = b.with_options(collector=collector).ValidateQuestionCategory(
                question=qa_pair.question,
                answer=qa_pair.ground_truth,
                current_category=str(qa_pair.category),
                **kwargs,
            )

            # Extract raw prompt from collector
            raw_prompt = None
            try:
                if collector.last and collector.last.calls:
                    first_call = collector.last.calls[0]

                    if hasattr(first_call, 'http_request') and first_call.http_request:
                        http_body = first_call.http_request.body

                        # Try text method first
                        if hasattr(http_body, 'text'):
                            try:
                                body_text = http_body.text()
                                if body_text:
                                    # Try to parse as JSON to extract messages
                                    try:
                                        body_json = json.loads(body_text)
                                        if isinstance(body_json, dict) and 'messages' in body_json:
                                            messages = body_json['messages']
                                            if messages and len(messages) > 0:
                                                # Get the system message content
                                                for msg in messages:
                                                    if msg.get('role') == 'system':
                                                        content = msg.get('content', '')
                                                        if isinstance(content, list) and len(content) > 0:
                                                            raw_prompt = content[0].get('text', '')
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
                        if not raw_prompt and hasattr(http_body, 'json'):
                            try:
                                body_json = http_body.json()
                                if isinstance(body_json, dict) and 'messages' in body_json:
                                    messages = body_json['messages']
                                    if messages and len(messages) > 0:
                                        # Get the system message content
                                        for msg in messages:
                                            if msg.get('role') == 'system':
                                                content = msg.get('content', '')
                                                if isinstance(content, list) and len(content) > 0:
                                                    raw_prompt = content[0].get('text', '')
                                                elif isinstance(content, str):
                                                    raw_prompt = content
                                                break
                                elif isinstance(body_json, str):
                                    raw_prompt = body_json
                            except Exception:
                                pass

                        # Try raw method as last resort
                        if not raw_prompt and hasattr(http_body, 'raw'):
                            try:
                                body_raw = http_body.raw()
                                if isinstance(body_raw, bytes):
                                    body_raw = body_raw.decode('utf-8')
                                raw_prompt = body_raw
                            except Exception:
                                pass
            except Exception as e:
                _logger.warning(f"Could not extract raw prompt: {e}")

            # Parse validated category to integer
            try:
                validated_category = int(validation_result.validated_category)
            except ValueError:
                _logger.error(f"Invalid category format: {validation_result.validated_category}")
                validated_category = qa_pair.category

            # Create new IfcBench instance with validated category
            validated_qa_pair = IfcBench(
                id=qa_pair.id,
                question=qa_pair.question,
                ground_truth=qa_pair.ground_truth,
                ifc_id=qa_pair.ifc_id,
                category=validated_category,
            )

            # Log outputs (including raw prompt)
            validator_span.set_outputs(
                {
                    "original_category": qa_pair.category,
                    "validated_category": validated_category,
                    "thought": validation_result.thought,
                    "raw_prompt": raw_prompt,
                }
            )

            # Calculate metrics
            duration = time.time() - start

            # Log attributes and metric
            validator_span.set_attributes(
                {
                    "duration": duration,
                    "original_category": qa_pair.category,
                    "validated_category": validated_category,
                    "reasoning": validation_result.thought,
                }
            )

            # Log metric for category update
            mlflow.log_metric("category_updated", 1 if validation_result.updated else 0)

            return validated_qa_pair

        except Exception as e:
            _logger.error(f"Error validating category for QA pair {qa_pair.id}: {e}")

            # Log error
            validator_span.set_outputs(
                {
                    "error": str(e),
                    "returned_original": True,
                }
            )

            # Calculate duration even on error
            duration = time.time() - start
            validator_span.set_attributes(
                {
                    "duration": duration,
                    "category_updated": False,
                    "error_occurred": True,
                }
            )

            # Log metric for no update due to error
            mlflow.log_metric("category_updated", 0)

            # Return original qa_pair on error
            return qa_pair


if __name__ == "__main__":
    import mlflow

    # Set up MLflow tracking
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("CategoryValidation")

    # Test 1: Category 1 - Direct retrieval (correctly classified)
    test_qa_pair_1 = IfcBench(
        id=1,
        question="What is the width of the entrance door?",
        ground_truth="The entrance door has a width of 900mm.",
        ifc_id=1,
        category=1,
    )

    print("Test 1: Category 1 - Direct Retrieval (Correctly Classified)")
    print(f"Original: Question='{test_qa_pair_1.question}', Category={test_qa_pair_1.category}")
    validated_1 = validate_category(test_qa_pair_1)
    print(f"Validated: Category={validated_1.category}")
    print()

    # Test 2: Category 2 - Should be 2, but marked as 1 (misclassified)
    test_qa_pair_2 = IfcBench(
        id=2,
        question="How many windows are in the building?",
        ground_truth="There are 45 windows in the building.",
        ifc_id=1,
        category=1,  # Wrong! Should be 2
    )

    print("Test 2: Category 2 - Aggregation (Misclassified as 1)")
    print(f"Original: Question='{test_qa_pair_2.question}', Category={test_qa_pair_2.category}")
    validated_2 = validate_category(test_qa_pair_2)
    print(f"Validated: Category={validated_2.category}")
    print()

    # Test 3: Category 3 - Geometric computation (correctly classified)
    test_qa_pair_3 = IfcBench(
        id=3,
        question="What is the Gross Floor Area of level 1?",
        ground_truth="The Gross Floor Area of level 1 is 1,250.5 m².",
        ifc_id=1,
        category=3,
    )

    print("Test 3: Category 3 - Geometric Computation (Correctly Classified)")
    print(f"Original: Question='{test_qa_pair_3.question}', Category={test_qa_pair_3.category}")
    validated_3 = validate_category(test_qa_pair_3)
    print(f"Validated: Category={validated_3.category}")
    print()

    # Test 4: Category 2 - List with aggregation (borderline case)
    test_qa_pair_4 = IfcBench(
        id=4,
        question="What types of pipes are used in the building, including their quantities?",
        ground_truth="Total Pipe Segments: 60\nPipe Types:\n- hwa afvoer: 60 segments",
        ifc_id=1,
        category=1,  # Wrong! Should be 2 due to aggregation
    )

    print("Test 4: Category 2 - List with Aggregation (Misclassified as 1)")
    print(f"Original: Question='{test_qa_pair_4.question}', Category={test_qa_pair_4.category}")
    validated_4 = validate_category(test_qa_pair_4)
    print(f"Validated: Category={validated_4.category}")
    print()

    # Test 5: Category 4 - Incomplete information
    test_qa_pair_5 = IfcBench(
        id=5,
        question="What is the Global Warming Potential of this building?",
        ground_truth="The GWP cannot be determined as material carbon factors are not stored in the BIM model.",
        ifc_id=1,
        category=4,
    )

    print("Test 5: Category 4 - Incomplete Information (Correctly Classified)")
    print(f"Original: Question='{test_qa_pair_5.question}', Category={test_qa_pair_5.category}")
    validated_5 = validate_category(test_qa_pair_5)
    print(f"Validated: Category={validated_5.category}")
