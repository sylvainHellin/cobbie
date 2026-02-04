"""
Agent that identifies faulty tools from wrong answers.
Analyzes failed Cobbie executions to identify helper functions that returned incorrect results.
"""

import time
from typing import Tuple

import mlflow
from baml_py.baml_py import Collector

from src.baml.baml_client import b
from src.baml.baml_client.types import FaultyToolAnalysis
from src.schemas.agent_error import AgentError
from src.util import setup_logger
from src.util.baml_retry import call_baml_with_retry
from src.agents import derive_binary_classification

setup_logger()

def identify_faulty_tool(
    history: str,
    question: str,
    ground_truth: str,
    provided_answer: str,
    justification: str,
    existing_helper_functions: str,
    llm_provider: str = "zai",
    llm_name: str = "GLM-4.6",
    **kwargs,
) -> Tuple[FaultyToolAnalysis | AgentError, Collector]:
    """
    Analyze a failed Cobbie execution to identify faulty helper functions.

    This function examines execution histories where Cobbie provided a wrong answer
    to determine if the failure was caused by a faulty tool (helper function that
    returned incorrect results) versus other causes like missing tools, reasoning
    errors, or incorrect tool usage.

    Args:
        history: Complete execution history from Cobbie (thoughts, code, results, final answer)
        question: The question that Cobbie attempted to answer
        ground_truth: The correct/expected answer to the question
        provided_answer: The incorrect answer that Cobbie provided
        justification: Justification from the answer verifier explaining why the answer was classified as wrong
        existing_helper_functions: List of all existing helper functions with docstrings and signatures
        llm_provider: LLM provider name for logging (default: "zai")
        llm_name: LLM model name for logging (default: "GLM-4.6")
        **kwargs: Additional arguments passed to BAML function

    Returns:
        Tuple of (FaultyToolAnalysis, Collector) where FaultyToolAnalysis contains:
        - thoughts: Chain-of-thought analysis of the execution history
        - faulty_tool: Whether a faulty tool was identified as the primary cause
        - faulty_tool_name: Name of the faulty tool (empty string if not applicable)
        - error_description: Summary of the error and test cases (empty string if not applicable)
        - confidence: Confidence level in this identification (high, medium, low)
    """
    # Start timer
    start = time.time()

    # Create collector for token tracking
    collector = Collector(name="FaultyNewToolAnalysis")

    # Add collector to kwargs for BAML calls
    if "baml_options" not in kwargs:
        kwargs["baml_options"] = {}
    kwargs["baml_options"]["collector"] = collector

    with mlflow.start_span(
        name="FaultyNewToolAnalysis", span_type="LLM"
    ) as identifier_span:
        identifier_span.set_inputs(
            {
                "history": history,
                "question": question,
                "ground_truth": ground_truth,
                "provided_answer": provided_answer,
                "justification": justification,
                "existing_helper_functions": existing_helper_functions,
            }
        )

        # Identify faulty tool
        baml_options = kwargs.pop("baml_options", {})
        faulty_tool_analysis = call_baml_with_retry(
            lambda: b.with_options(**baml_options).FaultyNewToolAnalysis(
                history=history,
                question=question,
                ground_truth=ground_truth,
                provided_answer=provided_answer,
                justification=justification,
                existing_helper_functions=existing_helper_functions,
                **kwargs,
            ),
            context_name="FaultyNewToolAnalysis",
        )

        if isinstance(faulty_tool_analysis, AgentError):
            return faulty_tool_analysis, collector

        # Log outputs
        identifier_span.set_outputs(
            {
                "thoughts": faulty_tool_analysis.thoughts,
                "faulty_tool": faulty_tool_analysis.faulty_tool,
                "faulty_tool_name": faulty_tool_analysis.faulty_tool_name,
                "error_description": faulty_tool_analysis.error_description,
                "confidence": faulty_tool_analysis.confidence,
            }
        )

        # Calculate metrics
        duration = time.time() - start
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0
        if collector.last:
            usage = collector.last.usage
            input_tokens = usage.input_tokens or 0
            output_tokens = usage.output_tokens or 0
            total_tokens = input_tokens + output_tokens

        # Log metrics
        identifier_span.set_attributes(
            {
                "duration": duration,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "llm_provider": llm_provider,
                "llm_name": llm_name,
                "faulty_tool_identified": faulty_tool_analysis.faulty_tool,
            }
        )

        return faulty_tool_analysis, collector


if __name__ == "__main__":
    import mlflow
    import ifcopenshell

    from src.agents.cobbie import cobbie
    from src.agents.answer_verifier import verify_answer
    from src.config import TEST_IFC_PATH
    from src.tools.initial import query_ifcopenshell_docs

    # Define a FAULTY helper function for testing purposes
    # BUG: This function ignores the floor_name parameter and returns ALL doors
    def count_doors_by_floor(ifc_file_path: str) -> int:
        """
        Count the number of doors on a specific building floor.

        Args:
            ifc_file_path: Path to the IFC file

        Returns:
            Number of doors on the specified floor
        """
        ifc_file = ifcopenshell.open(ifc_file_path)
        doors = ifc_file.by_type('IfcDoor') #type: ignore

        # BUG: Returns ALL doors instead of filtering by floor_name
        return len(doors)

    # Try to set up MLflow tracking, but don't fail if server is not available
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("FaultyNewToolAnalysis")

    # Setup tools for cobbie - INCLUDING THE FAULTY TOOL
    tools_dict = {
        "query_ifcopenshell_docs": query_ifcopenshell_docs,
        "count_doors_by_floor": count_doors_by_floor,  # This tool has a bug!
    }

    # Test question that Cobbie will answer incorrectly due to the faulty tool
    test_question = "How many doors are on the ground floor?"
    model_path = TEST_IFC_PATH

    # Ground truth: there are actually 6 doors on Level 1 (ground floor)
    # But the faulty tool will return 14 (all doors in the building)
    ground_truth = "There are 6 doors on the ground floor."

    print("=" * 80)
    print("STEP 1: Running Cobbie to answer the question")
    print("=" * 80)
    print(f"Question: {test_question}")
    print(f"Model Path: {model_path}")
    print(f"Ground Truth: {ground_truth}\n")

    # Run cobbie to get the answer and execution history
    with mlflow.start_run(run_name="FaultyNewToolAnalysis_Test"):
        cobbie_response = cobbie(
            user_input=test_question,
            tools=tools_dict,
            max_iterations=10,
            model_path=model_path,
            llm_provider="zai",
            llm_name="GLM-4.6",
        )

        print(f"\nCobbie Answer: {cobbie_response.answer.answer if cobbie_response.answer else 'No answer'}")
        print(f"Cobbie Reasoning: {cobbie_response.answer.thoughts if cobbie_response.answer else 'No thoughts'}\n")

        # Add final answer to the execution history
        full_history = f"""
{cobbie_response.history}

--- Final Answer ---
Thoughts: {cobbie_response.answer.thoughts if cobbie_response.answer else 'No thoughts'}
Answer: {cobbie_response.answer.answer if cobbie_response.answer else 'No answer'}
        """.strip()

        print("=" * 80)
        print("STEP 2: Verifying the answer")
        print("=" * 80)

        # Verify if the answer is correct
        verification_result, verification_collector = verify_answer(
            question=test_question,
            category=1,  # Category 1 for counting questions
            ground_truth=ground_truth,
            system_response=cobbie_response.answer.answer if cobbie_response.answer else "",
        )

        if isinstance(verification_result, AgentError):
            print(f"Error: {verification_result.error_message}")
            classification = "abstained"
        else:
            classification = derive_binary_classification(result=verification_result)

        print(f"\nClassification: {classification}")
        if not isinstance(verification_result, AgentError):
            print(f"Justification: {verification_result.justification}")

        # Only proceed with faulty tool identification if answer was wrong
        if classification == "wrong":
            print("=" * 80)
            print("STEP 3: Analyzing for faulty tools (answer was WRONG)")
            print("=" * 80)

            # Construct existing helper functions string
            test_existing_functions = """
def query_ifcopenshell_docs(query: str) -> str:
    '''Search ifcopenshell documentation for information'''

def count_doors_by_floor(ifc_file_path: str, floor_name: str) -> int:
    '''Count the number of doors on a specific building floor.

    Args:
        ifc_file_path: Path to the IFC file
        floor_name: Name of the floor/storey (e.g., 'Level 1', 'Ground Floor')

    Returns:
        Number of doors on the specified floor
    '''
            """.strip()

            # Analyze the failed execution for faulty tools
            faulty_tool_result, faulty_tool_collector = identify_faulty_tool(
                history=full_history,
                question=test_question,
                ground_truth=ground_truth,
                provided_answer=cobbie_response.answer.answer if cobbie_response.answer else "",
                justification=verification_result.justification if not isinstance(verification_result, AgentError) else "",
                existing_helper_functions=test_existing_functions,
            )

            print("\nBAML Faulty Tool Identifier Test Results:")
            if isinstance(faulty_tool_result, AgentError):
                print(f"Error: {faulty_tool_result.error_message}")
            else:
                print(f"\nFaulty Tool Identified: {faulty_tool_result.faulty_tool}")
                if faulty_tool_result.faulty_tool:
                    print(f"Tool Name: {faulty_tool_result.faulty_tool_name}")
                    print(f"Confidence: {faulty_tool_result.confidence}")
                    print(f"\nError Description:\n{faulty_tool_result.error_description}")
                print(f"\nThoughts:\n{faulty_tool_result.thoughts}")

            # Extract metrics
            faulty_tool_input_tokens = 0
            faulty_tool_output_tokens = 0
            if faulty_tool_collector and hasattr(faulty_tool_collector, "usage") and faulty_tool_collector.usage:
                usage = faulty_tool_collector.usage
                faulty_tool_input_tokens = usage.input_tokens or 0
                faulty_tool_output_tokens = usage.output_tokens or 0

            print("\n" + "=" * 80)
            print("Token Metrics Summary:")
            print("=" * 80)
            cobbie_input = cobbie_response.collector.usage.input_tokens if cobbie_response.collector and cobbie_response.collector.usage else 0
            cobbie_output = cobbie_response.collector.usage.output_tokens if cobbie_response.collector and cobbie_response.collector.usage else 0
            print(f"Cobbie - Input: {cobbie_input}, Output: {cobbie_output}")
            print(f"Answer Verifier - Input: {verification_collector.usage.input_tokens if verification_collector.usage else 0}, "
                  f"Output: {verification_collector.usage.output_tokens if verification_collector.usage else 0}")
            print(f"Faulty Tool Identifier - Input: {faulty_tool_input_tokens}, Output: {faulty_tool_output_tokens}")
            print("=" * 80)
        else:
            print("=" * 80)
            print("=" * 80)
            print("\nNo need to analyze for faulty tools since the answer was correct or abstained.")
            print("The faulty_tool_identifier agent is only run when answers are classified as 'wrong'.")
