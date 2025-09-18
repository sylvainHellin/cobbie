"""
Simple Python executor that runs in-process with security restrictions.

This executor only returns console logs (stdout/stderr), eliminating complex
result extraction logic. The agent should handle completion via output fields.
"""

import io
import sys
from typing import Callable, Dict, Optional

import tiktoken

from src.config import LOG_LEVEL
from src.engine.util import get_logger


class PythonInterpreter:
    """Simple in-process Python executor with read-only filesystem security."""

    def __init__(
        self,
        additional_authorized_functions: Optional[Dict[str, Callable]] = None,
        max_tokens_logs: int = 2**12,
    ):
        """
        Initialize the simple Python executor.

        Args:
            additional_authorized_functions: Additional functions beyond defaults
            max_tokens_logs: Maximum tokens for log output
        """
        from src.engine.tools.primordial.python_interpreter import AUTHORIZED_FUNCTIONS

        self.max_tokens_logs = max_tokens_logs
        self.logger = get_logger("PythonInterpreter", log_level=LOG_LEVEL)

        # Build function dictionary - all functions are directly available
        self.static_tools = AUTHORIZED_FUNCTIONS.copy()
        if additional_authorized_functions:
            self.static_tools.update(additional_authorized_functions)

        # Set up security restrictions
        self._setup_security()

    def _setup_security(self):
        """Set up read-only filesystem security."""
        # Store original functions
        self._original_open = __builtins__.get("open", open)

        # Create secure version
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
        """
        Execute Python code in a secure in-process environment.

        Args:
            code_action: Python code to execute

        Returns:
            Console output (logs) as string
        """
        self.logger.debug(f"Executing code: {code_action[:100]}...")

        # Capture stdout and stderr
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        original_stdout = sys.stdout
        original_stderr = sys.stderr

        sys.stdout = stdout_capture
        sys.stderr = stderr_capture

        # Set up execution environment
        execution_globals = {
            # All authorized functions
            **self.static_tools,
            # Standard built-ins
            "__builtins__": __builtins__,
            # Override open function directly - this takes precedence
            "open": self.secure_open,
        }

        execution_locals = {}
        logs = ""

        try:
            # Execute the code
            exec(code_action, execution_globals, execution_locals)

            # Get stdout content
            stdout_content = stdout_capture.getvalue()
            stderr_content = stderr_capture.getvalue()

            # Combine outputs
            if stdout_content and stderr_content:
                logs = f"{stdout_content}\n--- stderr ---\n{stderr_content}"
            elif stdout_content:
                logs = stdout_content
            elif stderr_content:
                logs = f"--- stderr ---\n{stderr_content}"
            else:
                logs = ""

        except Exception as e:
            logs = f"Execution error: {str(e)}"
            self.logger.error(f"Execution error: {e}")

        finally:
            sys.stdout = original_stdout
            sys.stderr = original_stderr

        # Truncate output if needed
        logs = self._truncate_text(logs, self.max_tokens_logs)

        self.logger.debug("Execution completed")
        return logs


def create_simple_interpreter(
    max_tokens_logs: int = 2**12,
    additional_authorized_functions: Optional[Dict[str, Callable]] = None,
) -> Callable:
    """
    Create a simple Python interpreter function.

    This provides a clean interface that only returns console logs,
    while maintaining read-only filesystem security.

    Args:
        max_tokens_logs: Maximum tokens for log output
        additional_authorized_functions: Additional custom functions

    Returns:
        A callable interpreter function with signature: python_code -> logs
    """
    executor = PythonInterpreter(
        additional_authorized_functions=additional_authorized_functions,
        max_tokens_logs=max_tokens_logs,
    )

    def python_interpreter(python_code: str) -> str:
        """
        Execute Python code and return console output.

        Args:
            python_code: The Python code to execute as a string

        Returns:
            Console output (stdout/stderr) as string
        """
        return executor(python_code)

    return python_interpreter
