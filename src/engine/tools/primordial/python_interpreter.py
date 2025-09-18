"""
Enhanced Python interpreter with comprehensive authorization lists.

This module provides a secure Python code execution environment with
extensive support for commonly used Python functions and imports.
The authorization lists are designed to be imported by other modules
to maintain consistency across the codebase.
"""

import math
from typing import Any, Callable, Dict, Optional

import tiktoken

from src.config import LOG_LEVEL
from src.engine.util import get_logger

# =============================================================================
# PYTHON TOOLS - Replaces smolagents BASE_PYTHON_TOOLS
# =============================================================================


def custom_print(*args, **kwargs):
    """Custom print function that mimics smolagents behavior"""
    print(*args, **kwargs)


def nodunder_getattr(obj, name):
    """Safe getattr that blocks dunder attributes"""
    if name.startswith("__") and name.endswith("__"):
        raise AttributeError(f"Access to dunder attribute '{name}' is forbidden")
    return getattr(obj, name)


def _build_base_python_tools() -> Dict[str, Any]:
    """
    Build the base Python tools dictionary to replace smolagents BASE_PYTHON_TOOLS.

    Returns:
        Dictionary mapping function names to callable objects and types
    """
    # Get builtins (not used but kept for potential future use)
    # builtins_dict = (
    #     __builtins__ if isinstance(__builtins__, dict) else __builtins__.__dict__
    # )

    # Core built-ins and types
    tools = {
        # Custom functions
        "print": custom_print,
        "getattr": nodunder_getattr,
        # Basic types and functions
        "isinstance": isinstance,
        "range": range,
        "float": float,
        "int": int,
        "bool": bool,
        "str": str,
        "set": set,
        "list": list,
        "dict": dict,
        "tuple": tuple,
        # Math functions from math module
        "round": round,
        "ceil": math.ceil,
        "floor": math.floor,
        "log": math.log,
        "exp": math.exp,
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "asin": math.asin,
        "acos": math.acos,
        "atan": math.atan,
        "atan2": math.atan2,
        "degrees": math.degrees,
        "radians": math.radians,
        "pow": pow,
        "sqrt": math.sqrt,
        # Sequence functions
        "len": len,
        "sum": sum,
        "max": max,
        "min": min,
        "abs": abs,
        "enumerate": enumerate,
        "zip": zip,
        "reversed": reversed,
        "sorted": sorted,
        "all": all,
        "any": any,
        "map": map,
        "filter": filter,
        # Other useful functions
        "ord": ord,
        "chr": chr,
        "next": next,
        "iter": iter,
        "divmod": divmod,
        "callable": callable,
        "hasattr": hasattr,
        "setattr": setattr,
        "issubclass": issubclass,
        "type": type,
        "complex": complex,
    }

    return tools


# The base Python tools dictionary
BASE_PYTHON_TOOLS = _build_base_python_tools()


# All standard built-ins for broader access
def _get_all_builtins() -> Dict[str, Any]:
    """Get all built-in functions for comprehensive access"""
    builtins_dict = (
        __builtins__ if isinstance(__builtins__, dict) else __builtins__.__dict__
    )

    # Filter out private and dangerous functions
    safe_builtins = {
        name: func
        for name, func in builtins_dict.items()
        if not name.startswith("_") and name not in ["exec", "eval", "compile"]
    }

    return safe_builtins


# Comprehensive default functions dictionary
AUTHORIZED_FUNCTIONS = {**BASE_PYTHON_TOOLS, **_get_all_builtins()}


def get_python_interpreter(
    max_tokens_logs: int = 2**12,
    additional_authorized_functions: Optional[Dict[str, Callable]] = None,
) -> Callable:
    """
    Create a Python interpreter with file security and function authorization.

    Security approach:
    - Allow ALL imports (no import restrictions)
    - Only restrict file system operations (read-only)
    - Provide comprehensive function access

    Args:
        max_tokens_logs: Maximum tokens for log output
        additional_authorized_functions: Additional custom functions beyond defaults

    Returns:
        A callable Python interpreter function
    """

    # Build function dictionary - no import restrictions needed
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

    # @mlflow.trace(
    #     name="PythonInterpreter",
    #     span_type=SpanType.TOOL,
    # )
    def python_interpreter(python_code: str) -> str:
        """
        Execute Python code and return console output.
        As this interpreter has no state, variables will not be carried over when this function is used again.

        Args:
            python_code: The Python code to execute as a string

        Returns:
            Console output (stdout/stderr) as string
        """
        logger = get_logger("python_interpreter", log_level=LOG_LEVEL)

        # Use the simplified secure executor
        from src.engine.tools.primordial._python_executor import (
            PythonInterpreter,
        )

        interpreter = PythonInterpreter(
            additional_authorized_functions=authorized_functions,
            max_tokens_logs=max_tokens_logs,
        )

        logger.debug("All imports allowed (no restrictions)")
        logger.debug(f"Authorized functions: {'; '.join(authorized_functions.keys())}")

        try:
            logs = interpreter(code_action=python_code)
            logger.debug("Tool execution completed successfully.")
            logger.debug(f"Console output (logs): {logs}")

        except Exception as e:
            logger.error(f"Execution failed: {e}")
            raise

        logs = _truncatenate_text(text=logs, max_tokens=max_tokens_logs)
        logger.info(f"outputs : {logs[:50]}...")

        return logs

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
        "authorized_functions": list(AUTHORIZED_FUNCTIONS.keys()),
        "imports_count": "unlimited",  # All imports are allowed
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
PYTHON INTERPRETER SECURITY:
- Import restrictions: NONE - All imports are allowed
- File operations: READ-ONLY - Writing/deleting files is blocked
- Authorized functions ({info["functions_count"]} total): {", ".join(info["authorized_functions"][:20])}{"..." if len(info["authorized_functions"]) > 20 else ""}
- LIMITATION: Dunder attributes like __name__, __doc__ may be restricted for security
- Alternative: Use string literals or inspect module for function metadata
- help(), dir(), globals() are permitted for debugging
"""


# =============================================================================
# TESTS AND EXAMPLES
# =============================================================================

if __name__ == "__main__":

    def test_basic_execution_1():
        print("Running test: basic execution with print allowed")
        code = 'print("Hello")\nprint("World")'
        interpreter = get_python_interpreter()
        result = interpreter(code)
        assert "Hello" in result
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
