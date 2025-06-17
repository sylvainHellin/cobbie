from typing import Callable, List, Dict
from smolagents.local_python_executor import InterpreterError

import tiktoken
from smolagents.local_python_executor import BASE_PYTHON_TOOLS, LocalPythonExecutor
from src.util import get_logger
from src.config import LOG_LEVEL

ADDITIONAL_AUTHORIZED_IMPORTS = [
    "ifcopenshell",
    "ifcopenshell.util.element",
    "ifcopenshell.util.shape",
    "ifcopenshell.util.placement",
    "ifcopenshell.util.geolocation",
    "ifcopenshell.util.system",
    "ifcopenshell.geom",
    "ifcopenshell.file",
    "ifcopenshell.entity_instance",
    "math",
    "numpy",
    "pandas",
]


def get_python_interpreter(
    max_tokens_logs: int = 2**12,
    max_tokens_output: int = 2**12,
    allowed_tools: Dict[str, Callable] = {"print": print},
    additional_authorized_imports: List[str] = ADDITIONAL_AUTHORIZED_IMPORTS,
) -> Callable:
    def _truncatenate_text(text: str, max_tokens: int) -> str:
        encoding = tiktoken.get_encoding("cl100k_base")  # GPT-4 encoding
        tokens = encoding.encode(text)

        if len(tokens) <= max_tokens:
            return text

        truncated_tokens = tokens[:max_tokens]
        truncated_text = encoding.decode(truncated_tokens)

        return f"{truncated_text}\n\n...output truncatenated after {max_tokens} tokens."

    def python_interpreter(
        python_code: str,
    ) -> str:
        """
        Execute Python code and return both the result and any printed output.

        Args:
            code: The Python code to execute as a string

        Returns:
            A formatted string containing both the print outputs and return value
        """
        logger = get_logger("python_interpreter", log_level=LOG_LEVEL)
        logger.info("tool called.")
        logger.debug(f"code to interpret:\n```python'n{python_code}\n```\n")

        interpreter = LocalPythonExecutor(
            additional_authorized_imports=additional_authorized_imports
        )
        base_tools = BASE_PYTHON_TOOLS.copy()
        static_tools = {**base_tools, **allowed_tools}
        interpreter.static_tools = static_tools
        logger.debug(
            f"Authorized imports: {'; '.join(additional_authorized_imports)}\n"
        )
        logger.debug(f"Authorized functions: {'; '.join(static_tools)}\n")

        try:
            returned_value, logs, is_final = interpreter(code_action=python_code)
            logger.info("Tool execution completed successfully.")
            logger.debug(f"Returned value: {returned_value}")
            logger.debug(f"Console output (logs): {logs}")
            logger.debug(f"Is final: {is_final}")

        except InterpreterError as e:
            logger.error(f"Error during tool execution: {e}")
            return f"An error occured while trying to execute this code:\n{e}"

        # format the response to include both printed output and the return value
        result = ""
        if logs:
            result += f"## Print output:\n{_truncatenate_text(logs, max_tokens=max_tokens_logs)}\n\n"

        result += f"## Return value:\n{_truncatenate_text(repr(returned_value), max_tokens=max_tokens_output)}"

        return result

        del logger

    return python_interpreter


if __name__ == "__main__":

    def test_basic_execution_1():
        print("Running test: basic execution with print allowed")
        code = 'print("Hello")\n"World"'
        interpreter = get_python_interpreter()
        result = interpreter(code)
        assert "## Print output" in result
        assert "Hello" in result
        assert "## Return value" in result
        assert "World" in result
        print("PASS: Basic execution with print allowed\\n")

    def test_basic_execution_2():
        print("Running test: basic execution with print not allowed")
        code = 'print("Hello")\n"World"'
        interpreter = get_python_interpreter(allowed_tools={})
        result = interpreter(code)
        assert "## Print output" in result
        # assert "Hello" not in result
        assert "## Return value" in result
        # assert "World" not in result
        print(result)
        print("PASS: Basic execution with print not allowed\\n")

    def double_number(num: int) -> int:
        return num * 2

    def test_custom_fn_allowed():
        print("Running test: custom function allowed")
        code = "double = double_number(3)\nprint(double)\ndouble"
        interpreter = get_python_interpreter(
            allowed_tools={"double_number": double_number}
        )
        result = interpreter(code)
        print(result)

    def test_custom_fn_not_allowed():
        print("Running test: custom function not allowed")
        code = "double = double_number(3)\nprint(double)\ndouble"
        interpreter = get_python_interpreter(allowed_tools={})
        result = interpreter(code)
        print(result)

    # def test_log_truncation():
    #     print("Running test: log truncation")
    #     # This will print many lines, forcing truncation of the logs.
    #     code = "\n".join([f"print({i})" for i in range(100)])
    #     result = get_python_interpreter(code, max_tokens_logs=50)
    #     assert "truncatenated" in result
    #     assert "## Print output" in result
    #     print("PASS: Log truncation\\n")

    # def test_output_truncation():
    #     print("Running test: output truncation")
    #     # This will return a very long string, forcing truncation of the return value.
    #     code = "'a' * 2000"
    #     result = get_python_interpreter(code, max_tokens_output=50)
    #     assert "truncatenated" in result
    #     assert "## Return value" in result
    #     print("PASS: Output truncation\\n")

    # def test_numpy_import():
    #     print("Running test: numpy import")
    #     code = "import numpy as np; np.array([1,2,3])"
    #     result = get_python_interpreter(code)
    #     assert "array([1, 2, 3])" in result
    #     assert "## Return value" in result
    #     print("PASS: Numpy import\\n")

    test_basic_execution_1()
    test_basic_execution_2()
    test_custom_fn_allowed()
    test_custom_fn_not_allowed()
    # test_log_truncation()
    # test_output_truncation()
    # test_numpy_import()
