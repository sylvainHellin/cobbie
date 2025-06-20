"""
Enhanced Python interpreter with comprehensive authorization lists.

This module provides a secure Python code execution environment with
extensive support for commonly used Python functions and imports.
The authorization lists are designed to be imported by other modules
to maintain consistency across the codebase.
"""

from typing import Callable, List, Dict, Any, Optional
from smolagents.local_python_executor import InterpreterError

import tiktoken
from smolagents.local_python_executor import BASE_PYTHON_TOOLS, LocalPythonExecutor
from src.engine.util import get_logger
from src.config import LOG_LEVEL

# =============================================================================
# GLOBAL AUTHORIZATION LISTS - Import these in other modules for consistency
# =============================================================================

# Comprehensive list of authorized imports
AUTHORIZED_IMPORTS = [
    # Core Python modules
    "math",
    "statistics",
    "random",
    "time",
    "datetime",
    "itertools",
    "collections",
    "re",
    "unicodedata",
    "queue",
    "stat",
    # Data science and numerical computing
    "numpy",
    "pandas",
    # Standard library utilities
    "json",
    "os",
    "sys",
    "pathlib",
    "glob",
    "shutil",
    "tempfile",
    "typing",
    "copy",
    "pickle",
    "base64",
    "hashlib",
    "uuid",
    "urllib",
    "urllib.parse",
    "urllib.request",
    # String and text processing
    "string",
    "textwrap",
    "difflib",
    "csv",
    # Development and debugging
    "inspect",
    "logging",
    "warnings",
    "traceback",
    "pprint",
    # Compression and archives
    "zipfile",
    "tarfile",
    "gzip",
    # IFC and BIM-specific imports
    "ifcopenshell",
    "ifcopenshell.*",  # Allow all ifcopenshell submodules
    "ifcopenshell.util.element",
    "ifcopenshell.util.shape",
    "ifcopenshell.util.placement",
    "ifcopenshell.util.geolocation",
    "ifcopenshell.util.system",
    "ifcopenshell.geom",
    "ifcopenshell.file",
    "ifcopenshell.entity_instance",
]

# Comprehensive list of authorized built-in function names
AUTHORIZED_FUNCTION_NAMES = [
    # Core built-ins from BASE_PYTHON_TOOLS
    "print",
    "isinstance",
    "range",
    "float",
    "int",
    "bool",
    "str",
    "set",
    "list",
    "dict",
    "tuple",
    "bytes",
    "bytearray",
    "memoryview",
    # Mathematical functions
    "round",
    "ceil",
    "floor",
    "log",
    "exp",
    "sin",
    "cos",
    "tan",
    "asin",
    "acos",
    "atan",
    "atan2",
    "degrees",
    "radians",
    "pow",
    "sqrt",
    # Sequence and collection functions
    "len",
    "sum",
    "max",
    "min",
    "abs",
    "enumerate",
    "zip",
    "reversed",
    "sorted",
    "all",
    "any",
    "map",
    "filter",
    "slice",
    # Type and object inspection
    "ord",
    "chr",
    "next",
    "iter",
    "divmod",
    "callable",
    "getattr",
    "hasattr",
    "setattr",
    "delattr",
    "issubclass",
    "type",
    "complex",
    "vars",
    "dir",
    "id",
    "hash",
    "repr",
    "ascii",
    "bin",
    "hex",
    "oct",
    # Advanced built-ins often needed for development
    "help",
    "globals",
    "locals",
    "eval",
    "exec",
    "compile",
    # File and I/O (be cautious with these)
    "open",
    "input",
    # Exception handling
    "BaseException",
    "Exception",
    "ValueError",
    "TypeError",
    "AttributeError",
    "IndexError",
    "KeyError",
    "FileNotFoundError",
    "RuntimeError",
]


def _build_default_authorized_functions() -> Dict[str, Callable]:
    """
    Build the comprehensive default functions dictionary.

    Returns:
        Dictionary mapping function names to callable objects
    """
    # Start with BASE_PYTHON_TOOLS
    base_tools = BASE_PYTHON_TOOLS.copy()

    # Handle __builtins__ being either a dict or module
    builtins_dict = (
        __builtins__ if isinstance(__builtins__, dict) else __builtins__.__dict__
    )

    # Add additional built-ins from our comprehensive list
    additional_builtins = {
        name: builtins_dict[name]
        for name in AUTHORIZED_FUNCTION_NAMES
        if name in builtins_dict and name not in base_tools
    }

    return {**base_tools, **additional_builtins}


# Comprehensive default functions dictionary
AUTHORIZED_FUNCTIONS = _build_default_authorized_functions()

# Backward compatibility - keep the old name
ADDITIONAL_AUTHORIZED_IMPORTS = AUTHORIZED_IMPORTS


def get_python_interpreter(
    max_tokens_logs: int = 2**12,
    max_tokens_output: int = 2**12,
    additional_authorized_functions: Optional[Dict[str, Callable]] = None,
    additional_authorized_imports: Optional[List[str]] = None,
) -> Callable:
    """
    Create a Python interpreter with enhanced security and comprehensive authorization.

    Both functions and imports follow the same pattern:
    - Start with comprehensive defaults (AUTHORIZED_FUNCTIONS, AUTHORIZED_IMPORTS)
    - Extend with additional custom items if provided

    Args:
        max_tokens_logs: Maximum tokens for log output
        max_tokens_output: Maximum tokens for return value output
        additional_authorized_functions: Additional custom functions beyond the comprehensive defaults
        additional_authorized_imports: Additional imports beyond the comprehensive defaults

    Returns:
        A callable Python interpreter function
    """

    # Use comprehensive defaults, extend with additional if provided
    authorized_imports = AUTHORIZED_IMPORTS.copy()
    if additional_authorized_imports:
        authorized_imports.extend(additional_authorized_imports)

    authorized_functions = AUTHORIZED_FUNCTIONS.copy()
    if additional_authorized_functions:
        authorized_functions.update(additional_authorized_functions)

    def _truncatenate_text(text: str, max_tokens: int) -> str:
        """Truncate text to specified token limit."""
        encoding = tiktoken.get_encoding("cl100k_base")  # GPT-4 encoding
        tokens = encoding.encode(text)

        if len(tokens) <= max_tokens:
            return text

        truncated_tokens = tokens[:max_tokens]
        truncated_text = encoding.decode(truncated_tokens)

        return f"{truncated_text}\n\n...output truncated after {max_tokens} tokens."

    def python_interpreter(python_code: str) -> str:
        """
        Execute Python code and return both the result and any printed output.
        As this interpreter has no state, variables will not be carried over when this function is used again.

        Args:
            python_code: The Python code to execute as a string

        Returns:
            A formatted string containing both the print outputs and return value
        """
        logger = get_logger("python_interpreter", log_level=LOG_LEVEL)
        logger.info("tool called.")
        logger.debug(f"code to interpret:\n```python\n{python_code}\n```\n")

        interpreter = LocalPythonExecutor(
            additional_authorized_imports=authorized_imports
        )

        # Use the comprehensive default functions with any additional ones
        interpreter.static_tools = authorized_functions

        logger.debug(f"Authorized imports: {'; '.join(authorized_imports)}")
        logger.debug(f"Authorized functions: {'; '.join(authorized_functions.keys())}")

        try:
            returned_value, logs, is_final = interpreter(code_action=python_code)
            logger.info("Tool execution completed successfully.")
            logger.debug(f"Returned value: {returned_value}")
            logger.debug(f"Console output (logs): {logs}")
            logger.debug(f"Is final: {is_final}")

        except InterpreterError as e:
            logger.error(f"Error during tool execution: {e}")
            return f"An error occurred while trying to execute this code:\n{e}"

        # Format the response to include both printed output and the return value
        result = ""
        if logs:
            result += f"## Print output:\n{_truncatenate_text(logs, max_tokens=max_tokens_logs)}\n\n"

        result += f"## Return value:\n{_truncatenate_text(repr(returned_value), max_tokens=max_tokens_output)}"

        return result

    return python_interpreter


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def get_authorization_info() -> Dict[str, Any]:
    """
    Get information about current authorization settings.

    Returns:
        Dictionary containing authorization lists and counts
    """
    return {
        "authorized_imports": AUTHORIZED_IMPORTS,
        "authorized_functions": list(AUTHORIZED_FUNCTIONS.keys()),
        "imports_count": len(AUTHORIZED_IMPORTS),
        "functions_count": len(AUTHORIZED_FUNCTIONS),
    }


def format_restrictions_info() -> str:
    """
    Format authorization information for inclusion in prompts.

    Returns:
        Formatted string describing what's allowed
    """
    info = get_authorization_info()

    return f"""
PYTHON INTERPRETER RESTRICTIONS:
- Authorized imports ({info["imports_count"]} total): {", ".join(info["authorized_imports"][:20])}{"..." if len(info["authorized_imports"]) > 20 else ""}
- Authorized functions ({info["functions_count"]} total): {", ".join(info["authorized_functions"][:20])}{"..." if len(info["authorized_functions"]) > 20 else ""}
- Note: typing, os, json, inspect are now allowed
- LIMITATION: Dunder attributes like __name__, __doc__ are forbidden for security reaon.
- Alternative: Use string literals or inspect module for function metadata
- help(), dir(), globals() are permitted for debugging
"""


# =============================================================================
# TESTS AND EXAMPLES
# =============================================================================

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
        print("PASS: Basic execution with print allowed\n")

    def test_enhanced_functions():
        print("Running test: enhanced functions")
        code = """
import json
import os
from typing import List, Dict
import inspect

# Test various previously forbidden operations
data = {"test": "value"}
json_str = json.dumps(data)
print(f"JSON: {json_str}")

# Test typing
def example_func(items: List[str]) -> Dict[str, int]:
    return {item: len(item) for item in items}

result = example_func(["hello", "world"])
print(f"Typed function result: {result}")

# Test inspection
sig = inspect.signature(example_func)
print(f"Function signature: {sig}")

# Test help (should work now)
help(len)

result
"""
        interpreter = get_python_interpreter()
        result = interpreter(code)
        print(f"Result: {result}")
        print("PASS: Enhanced functions test\n")

    def test_restrictions_info():
        print("Running test: restrictions info")
        info = get_authorization_info()
        print(f"Total imports: {info['imports_count']}")
        print(f"Total functions: {info['functions_count']}")

        print("\nFormatted restrictions:")
        print(format_restrictions_info())
        print("PASS: Restrictions info test\n")

    def double_number(num: int) -> int:
        return num * 2

    def test_custom_fn_allowed():
        print("Running test: custom function allowed")
        code = "double = double_number(3)\nprint(double)\ndouble"
        interpreter = get_python_interpreter(
            additional_authorized_functions={"double_number": double_number}
        )
        result = interpreter(code)
        print(result)
        print("PASS: Custom function test\n")

    # Run tests
    test_basic_execution_1()
    test_enhanced_functions()
    test_restrictions_info()
    test_custom_fn_allowed()

    print("All tests completed!")
