from smolagents.local_python_executor import LocalPythonExecutor, BASE_PYTHON_TOOLS
import tiktoken


def python_interpreter(
    python_code: str, max_tokens_logs: int = 2**12, max_tokens_output: int = 2**12
) -> str:
    """
    Execute Python code and return both the result and any printed output.

    Args:
        code: The Python code to execute as a string

    Returns:
        A formatted string containing both the print outputs and return value
    """

    additional_authorized_imports = [
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

    interpreter = LocalPythonExecutor(
        additional_authorized_imports=additional_authorized_imports
    )
    allowed_tools = BASE_PYTHON_TOOLS.copy()
    allowed_tools["print"] = lambda *args: interpreter.state["_print_outputs"].__iadd__(
        " ".join(map(str, args)) + "\n"
    )
    interpreter.static_tools = allowed_tools

    returned_value, logs, is_final = interpreter(code_action=python_code)

    def truncatenate_text(text: str, max_tokens: int) -> str:
        encoding = tiktoken.get_encoding("cl100k_base")  # GPT-4 encoding
        tokens = encoding.encode(text)

        if len(tokens) <= max_tokens:
            return text

        truncated_tokens = tokens[:max_tokens]
        truncated_text = encoding.decode(truncated_tokens)

        return f"{truncated_text}\n\n...output truncatenated after {max_tokens} tokens."

    # format the response to include both printed output and the return value
    result = ""
    if logs:
        result += f"## Print output:\n{truncatenate_text(logs, max_tokens=max_tokens_logs)}\n\n"

    result += f"## Return value:\n{truncatenate_text(repr(returned_value), max_tokens=max_tokens_output)}"

    return result


if __name__ == "__main__":

    def test_basic_execution():
        print("Running test: basic execution")
        code = 'print("Hello")\n"World"'
        result = python_interpreter(code)
        assert "## Print output" in result
        assert "Hello" in result
        assert "## Return value" in result
        assert "World" in result
        print("PASS: Basic execution\\n")

    def test_log_truncation():
        print("Running test: log truncation")
        # This will print many lines, forcing truncation of the logs.
        code = "\n".join([f"print({i})" for i in range(100)])
        result = python_interpreter(code, max_tokens_logs=50)
        assert "truncatenated" in result
        assert "## Print output" in result
        print("PASS: Log truncation\\n")

    def test_output_truncation():
        print("Running test: output truncation")
        # This will return a very long string, forcing truncation of the return value.
        code = "'a' * 2000"
        result = python_interpreter(code, max_tokens_output=50)
        assert "truncatenated" in result
        assert "## Return value" in result
        print("PASS: Output truncation\\n")

    def test_numpy_import():
        print("Running test: numpy import")
        code = "import numpy as np; np.array([1,2,3])"
        result = python_interpreter(code)
        assert "array([1, 2, 3])" in result
        assert "## Return value" in result
        print("PASS: Numpy import\\n")

    test_basic_execution()
    test_log_truncation()
    test_output_truncation()
    test_numpy_import()
