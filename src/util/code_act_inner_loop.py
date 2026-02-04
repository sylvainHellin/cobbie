from typing import Any, Callable, Dict, Optional

import mlflow

from src.baml.baml_client import b
from src.baml.baml_client.types import CodeAction, FinalAnswer
from src.config import FUNCTION_BOILERPLATE
from src.schemas.agent_error import AgentError
from src.util.baml_retry import call_baml_with_retry
from src.util.python_executor import execute_python


def _execute_code_action(
    code_action: CodeAction,
    iteration: int,
    tools: Dict[str, Callable] = {},
    model_path: Optional[str] = None,
    add_code_prefix: bool = True,
    interpreter: Optional[Any] = None,
) -> str:
    """
    Execute a CodeAction from the agent return the the formated result of the attempt.
    """
    with mlflow.start_span(
        name=f"code_action_{iteration + 1}", span_type="TOOL"
    ) as code_action_span:
        # Extract the python code from the CodeAction
        python_code = code_action.python_code

        # Add the code prefix if so configured
        if add_code_prefix:
            code_prefix = FUNCTION_BOILERPLATE + "\n"

            if model_path is not None:
                code_prefix += f"\npath_ifc_model = '{model_path}'"
            python_code = f"{code_prefix}\n{python_code}"

        # Log the inputs
        code_action_span.set_inputs(
            {
                "thoughts": code_action.thoughts,
                "python_code": python_code,
            }
        )

        # Execute the code
        result_code_evaluation = execute_python(
            python_code=python_code,
            tools=tools,
            model_path=model_path,
            interpreter=interpreter,
        )

        # Update the previous attempt
        attempt = f"""
        --- Iteration {iteration + 1} ---
        Thoughts: {code_action.thoughts}

        Code:
        {python_code}

        Result:
        {result_code_evaluation}

        """

        # Log the outputs
        code_action_span.set_outputs({"result_code_evaluation": result_code_evaluation})

        return attempt


def _code_act_iter(
    user_input: str,
    available_tools: str,
    previous_attempts: Optional[str] = None,
    model_path: Optional[str] = None,
    **kwargs,
) -> CodeAction | FinalAnswer | AgentError:
    """
    Execute a single reasoning step using BAML.

    This function represents one iteration of the reasoning loop,
    calling the LLM to either generate code or provide a final answer.

    Args:
        user_input: The original question or task
        available_tools: Documentation of available tools
        previous_attempts: Results from previous iterations
        model_path: Optional path to IFC model file
        **kwargs: Additional arguments for BAML function (including baml_options)

    Returns:
        CodeAction to continue reasoning, FinalAnswer to stop, or AgentError on failure.
    """

    # Extract baml_options if provided for collector integration
    baml_options = kwargs.pop("baml_options", {})

    if baml_options:
        return call_baml_with_retry(
            lambda: b.with_options(**baml_options).Cobbie(
                user_input=user_input,
                available_tools=available_tools,
                previous_attempts=previous_attempts,
                model_path=model_path,
            ),
            context_name="Cobbie",
        )
    else:
        return call_baml_with_retry(
            lambda: b.Cobbie(
                user_input=user_input,
                available_tools=available_tools,
                previous_attempts=previous_attempts,
                model_path=model_path,
            ),
            context_name="Cobbie",
        )
