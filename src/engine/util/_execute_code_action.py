from typing import Dict, Callable, Optional
import mlflow
from baml_client.types import CodeAction

from src.engine.util.python_executor import execute_python
from src.config import FUNCTION_BOILERPLATE


def _execute_code_action(
    code_action: CodeAction,
    iteration: int,
    previous_attempt: str = "",
    tools: Dict[str, Callable] = {},
    model_path: Optional[str] = None,
    add_code_prefix: bool = True,
) -> str:
    """
    Execute a CodeAction from the agent to update and return the provided previous_attempt.
    """
    with mlflow.start_span(
        name=f"code_action_{iteration}", span_type="TOOL"
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
        )

        # Update the previous attempt
        previous_attempt += f"""
        --- Iteration {iteration + 1} ---
        Thoughts: {code_action.thoughts}

        Code:
        {python_code}

        Result:
        {result_code_evaluation}

        """

        # Log the outputs
        code_action_span.set_outputs({"result_code_evaluation": result_code_evaluation})

        return previous_attempt
