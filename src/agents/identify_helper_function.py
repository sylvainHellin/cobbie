"""
Agent that identify new helper functions.
Analyzes successful Cobbie executions to identify reusable helper functions.
"""

import time
from typing import Tuple

import mlflow
from baml_py.baml_py import Collector
from baml_client import b
from baml_client.types import NewToolAnalysis
from src.config import LOG_LEVEL
from src.engine.util import get_logger

# Initialize logger
_logger = get_logger(name="baml_helper_function_identifier", log_level=LOG_LEVEL)


def identify_helper_function(
    history: str,
    example_question: str,
    existing_helper_functions: str,
    llm_provider: str = "zai",
    llm_name: str = "GLM-4.6",
    **kwargs,
) -> Tuple[NewToolAnalysis, Collector]:
    """
    Analyze a successful Cobbie execution to identify reusable helper functions.

    Args:
        history: Complete execution history from Cobbie (thoughts, code, results, final answer)
        example_question: The question that was successfully answered by Cobbie
        existing_helper_functions: List of all existing helper functions with docstrings and signatures
        llm_provider: LLM provider name for logging (default: "zai")
        llm_name: LLM model name for logging (default: "GLM-4.6")
        **kwargs: Additional arguments passed to BAML function

    Returns:
        Tuple of (NewToolAnalysis, Collector) where NewToolAnalysis contains:
        - thoughts: Step-by-step analysis of the execution history
        - new_tool: Whether a new helper function should be created
        - new_tool_name: Suggested name for the new helper function
        - new_tool_description: Detailed description of the helper function
    """
    # Start timer
    start = time.time()

    # Create collector for token tracking
    collector = Collector(name="HelperFunctionIdentifier")

    # Add collector to kwargs for BAML calls
    if "baml_options" not in kwargs:
        kwargs["baml_options"] = {}
    kwargs["baml_options"]["collector"] = collector

    with mlflow.start_span(
        name="HelperFunctionIdentifier", span_type="LLM"
    ) as identifier_span:
        identifier_span.set_inputs(
            {
                "history": history,
                "example_question": example_question,
                "existing_helper_functions": existing_helper_functions,
            }
        )

        # Identify helper function
        try:
            tool_identification = b.with_options(
                **kwargs.pop("baml_options", {})
            ).HelperFunctionIdentifier(
                history=history,
                example_question=example_question,
                existing_helper_functions=existing_helper_functions,
                **kwargs,
            )
        except Exception as e:
            _logger.error(f"Error identifying helper function: {e}")
            tool_identification = NewToolAnalysis(
                thoughts=f"An Exception occurred when trying to identify helper function. Exception:\n{e}",
                new_tool=False,
                new_tool_name="",
                new_tool_description="",
            )

        # Log outputs
        identifier_span.set_outputs(
            {
                "thoughts": tool_identification.thoughts,
                "new_tool": tool_identification.new_tool,
                "new_tool_name": tool_identification.new_tool_name,
                "new_tool_description": tool_identification.new_tool_description,
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
            }
        )

        return tool_identification, collector


if __name__ == "__main__":
    import mlflow

    from src.agents.cobbie import cobbie
    from src.config import TEST_IFC_PATH
    from src.tools.initial import query_ifcopenshell_docs, web_search

    # Try to set up MLflow tracking, but don't fail if server is not available
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("HelperFunctionIdentifier")

    # Setup tools for cobbie
    tools_dict = {
        "query_ifcopenshell_docs": query_ifcopenshell_docs,
        "web_search": web_search,
    }

    # Test question that should generate a reusable pattern
    test_question = "How many doors are on the ground floor?"
    model_path = TEST_IFC_PATH

    print("="*80)
    print("STEP 1: Running Cobbie to answer the question")
    print("="*80)
    print(f"Question: {test_question}")
    print(f"Model Path: {model_path}\n")

    # Run cobbie to get the answer and execution history
    with mlflow.start_run(run_name="HelperFunctionIdentifier_Test"):
        cobbie_result, cobbie_collector, execution_history = cobbie(
            user_input=test_question,
            tools=tools_dict,
            max_iterations=10,
            model_path=model_path,
            llm_provider="zai",
            llm_name="GLM-4.6",
        )

        print(f"\nCobbie Answer: {cobbie_result.answer}")
        print(f"Cobbie Reasoning: {cobbie_result.thoughts}\n")

        # Add final answer to the execution history
        full_history = f"""
{execution_history}

--- Final Answer ---
Thoughts: {cobbie_result.thoughts}
Answer: {cobbie_result.answer}
        """.strip()

        print("="*80)
        print("STEP 2: Analyzing execution to identify helper functions")
        print("="*80)

        # Construct existing helper functions string
        test_existing_functions = """
def query_ifcopenshell_docs(query: str) -> str:
    '''Search ifcopenshell documentation for information'''

def web_search(query: str) -> str:
    '''Search the web for general information'''
        """.strip()

        # Test the functional helper function identifier
        result, collector = identify_helper_function(
            history=full_history,
            example_question=test_question,
            existing_helper_functions=test_existing_functions,
        )

        print("\nBAML Helper Function Identifier Test Results:")
        print(f"\nThoughts:\n{result.thoughts}")
        print(f"\nShould create new tool: {result.new_tool}")
        if result.new_tool:
            print(f"Tool name: {result.new_tool_name}")
            print(f"\nTool description:\n{result.new_tool_description}")

        # Extract metrics
        input_tokens = 0
        output_tokens = 0
        total_tokens = 0

        if collector and hasattr(collector, "usage") and collector.usage:
            usage = collector.usage
            input_tokens = usage.input_tokens or 0
            output_tokens = usage.output_tokens or 0
            total_tokens = input_tokens + output_tokens

        print("\n" + "="*80)
        print("Metrics:")
        print(f"Cobbie - Input Tokens: {cobbie_collector.usage.input_tokens if cobbie_collector.usage else 0}")
        print(f"Cobbie - Output Tokens: {cobbie_collector.usage.output_tokens if cobbie_collector.usage else 0}")
        print(f"Helper Function Identifier - Input Tokens: {input_tokens}")
        print(f"Helper Function Identifier - Output Tokens: {output_tokens}")
        print(f"Total Tokens: {(cobbie_collector.usage.input_tokens if cobbie_collector.usage else 0) + (cobbie_collector.usage.output_tokens if cobbie_collector.usage else 0) + total_tokens}")
        print("="*80)
