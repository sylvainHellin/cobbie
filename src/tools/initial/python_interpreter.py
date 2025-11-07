"""
Secure Python interpreter with comprehensive authorization and read-only filesystem security.
"""

import io
import math
import sys
import traceback
from typing import Any, Callable, Dict, Optional

import tiktoken

from src.config import LOG_LEVEL
from src.util import get_logger


def custom_print(*args, **kwargs):
    """Custom print function that mimics smolagents behavior"""
    print(*args, **kwargs)


def nodunder_getattr(obj, name):
    """Safe getattr that blocks dunder attributes"""
    if name.startswith("__") and name.endswith("__"):
        raise AttributeError(f"Access to dunder attribute '{name}' is forbidden")
    return getattr(obj, name)


def _build_base_python_tools() -> Dict[str, Any]:
    """Build the base Python tools dictionary."""
    tools = {
        "print": custom_print,
        "getattr": nodunder_getattr,
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


def _get_all_builtins() -> Dict[str, Any]:
    """Get all built-in functions for comprehensive access"""
    builtins_dict = (
        __builtins__ if isinstance(__builtins__, dict) else __builtins__.__dict__
    )

    safe_builtins = {
        name: func
        for name, func in builtins_dict.items()
        if not name.startswith("_") and name not in ["exec", "eval", "compile"]
    }

    return safe_builtins


BASE_PYTHON_TOOLS = _build_base_python_tools()
AUTHORIZED_FUNCTIONS = {**BASE_PYTHON_TOOLS, **_get_all_builtins()}


class PythonInterpreter:
    """Simple in-process Python executor with read-only filesystem security."""

    def __init__(
        self,
        additional_authorized_functions: Optional[Dict[str, Callable]] = None,
        max_tokens_logs: int = 2**12,
    ):
        self.max_tokens_logs = max_tokens_logs
        self.logger = get_logger("PythonInterpreter", log_level=LOG_LEVEL)

        self.static_tools = AUTHORIZED_FUNCTIONS.copy()
        if additional_authorized_functions:
            self.static_tools.update(additional_authorized_functions)

        self._setup_security()

    def _setup_security(self):
        """Set up read-only filesystem security."""
        self._original_open = __builtins__.get("open", open)

        def secure_open(file, mode="r", **kwargs):
            """Override open() to prevent write operations."""
            if any(m in str(mode) for m in ["w", "a", "x", "+"]):
                raise PermissionError(f"File writing is not allowed (mode: {mode})")
            return self._original_open(file, mode, **kwargs)

        self.secure_open = secure_open

    def _truncate_text(self, text: str, max_tokens: int) -> str:
        """Truncate text to specified token limit."""
        encoding = tiktoken.get_encoding("cl100k_base")
        tokens = encoding.encode(text)

        if len(tokens) <= max_tokens:
            return text

        truncated_tokens = tokens[:max_tokens]
        truncated_text = encoding.decode(truncated_tokens)
        return f"{truncated_text}\n\n...output truncated after {max_tokens} tokens."

    def __call__(self, code_action: str) -> str:
        """Execute Python code in a secure in-process environment."""
        self.logger.debug(f"Executing code: {code_action[:100]}...")

        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        original_stdout = sys.stdout
        original_stderr = sys.stderr

        sys.stdout = stdout_capture
        sys.stderr = stderr_capture

        execution_globals = {
            **self.static_tools,
            "__builtins__": __builtins__,
            "open": self.secure_open,
        }

        execution_locals = {}
        logs = ""

        try:
            exec(code_action, execution_globals, execution_locals)

            stdout_content = stdout_capture.getvalue()
            stderr_content = stderr_capture.getvalue()

            if stdout_content and stderr_content:
                logs = f"{stdout_content}\n--- stderr ---\n{stderr_content}"
            elif stdout_content:
                logs = stdout_content
            elif stderr_content:
                logs = f"--- stderr ---\n{stderr_content}"
            else:
                logs = ""

        except Exception as e:
            logs = f"Execution error:\n{traceback.format_exc()}"
            self.logger.error(f"Execution error: {e}")

        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr

        logs = self._truncate_text(logs, self.max_tokens_logs)
        self.logger.debug("Execution completed")
        return logs


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
    authorized_functions = AUTHORIZED_FUNCTIONS.copy()
    if additional_authorized_functions:
        authorized_functions.update(additional_authorized_functions)

    def _truncate_text(text: str, max_tokens: int) -> str:
        """Truncate text to specified token limit."""
        encoding = tiktoken.get_encoding("cl100k_base")
        tokens = encoding.encode(text)

        if len(tokens) <= max_tokens:
            return text

        truncated_tokens = tokens[:max_tokens]
        truncated_text = encoding.decode(truncated_tokens)
        return f"{truncated_text}\n\n...output truncated after {max_tokens} tokens."

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

        logs = _truncate_text(text=logs, max_tokens=max_tokens_logs)
        logger.info(f"outputs : {logs[:50]}...")

        return logs

    return python_interpreter


def get_authorization_info() -> Dict[str, Any]:
    """Get information about current authorization settings."""
    return {
        "authorized_functions": list(AUTHORIZED_FUNCTIONS.keys()),
        "imports_count": "unlimited",
        "functions_count": len(AUTHORIZED_FUNCTIONS),
    }


def format_restrictions_info() -> str:
    """Format authorization information for inclusion in prompts."""
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
