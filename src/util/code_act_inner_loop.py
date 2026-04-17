from typing import Any, Callable, Dict, Optional

import mlflow

from src.baml.baml_client.types import CodeAction
from src.config import FUNCTION_BOILERPLATE
from src.util.python_executor import execute_python_safe


def _execute_code_action(
    code_action: CodeAction,
    iteration: int,
    tools: Dict[str, Callable] = {},
    model_path: Optional[str] = None,
    add_code_prefix: bool = True,
    interpreter: Optional[Any] = None,
    boilerplate: Optional[str] = None,
) -> str:
    """
    Execute a CodeAction from the agent return the the formated result of the attempt.
    """
    with mlflow.start_span(
        name=f"code_action_{iteration + 1}", span_type="TOOL"
    ) as code_action_span:
        python_code = code_action.python_code

        if add_code_prefix:
            bp = boilerplate if boilerplate is not None else FUNCTION_BOILERPLATE
            code_prefix = bp + "\n"

            if model_path is not None:
                code_prefix += f"\npath_ifc_model = '{model_path}'"
            python_code = f"{code_prefix}\n{python_code}"

        code_action_span.set_inputs(
            {
                "thoughts": code_action.thoughts,
                "python_code": python_code,
            }
        )

        result_code_evaluation = execute_python_safe(
            python_code=python_code,
            tools=tools,
            model_path=model_path,
            timeout_seconds=300,
            interpreter=interpreter,
        )

        attempt = f"""
        --- Iteration {iteration + 1} ---
        Thoughts: {code_action.thoughts}

        Code:
        {python_code}

        Result:
        {result_code_evaluation}

        """

        code_action_span.set_outputs({"result_code_evaluation": result_code_evaluation})

        return attempt
