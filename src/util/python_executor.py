"""Python execution utilities for COBBIE and other components."""

import io
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Callable, Dict, Optional

import tiktoken
from loguru import logger


def count_tokens(text: str, model: str = "gpt-3.5-turbo") -> int:
    """
    Count the number of tokens in the given text using tiktoken.

    Args:
        text: The text to count tokens for
        model: The model name to use for tokenization (default: gpt-3.5-turbo)

    Returns:
        The number of tokens in the text
    """
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        # Fallback to a default encoding if the model is not found
        encoding = tiktoken.get_encoding("cl100k_base")

    return len(encoding.encode(text))


def truncate_to_tokens(text: str, max_tokens: int, model: str = "gpt-3.5-turbo") -> str:
    """
    Truncate text to a maximum number of tokens.

    Args:
        text: The text to truncate
        max_tokens: Maximum number of tokens
        model: The model name to use for tokenization

    Returns:
        Truncated text with warning message if truncation occurred
    """
    token_count = count_tokens(text, model)

    if token_count <= max_tokens:
        return text

    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")

    # Encode and truncate
    tokens = encoding.encode(text)
    truncated_tokens = tokens[:max_tokens]
    truncated_text = encoding.decode(truncated_tokens)

    warning_msg = f"\n...\nWARNING:\nOutput truncated due to excessive length ({token_count} tokens > {max_tokens} tokens limit)"

    return truncated_text + warning_msg


def setup_interpreter(
    model_path: Optional[str] = None,
    tools: Optional[Dict[str, Callable]] = None
) -> Any:
    """
    Setup Python interpreter with tools and model context.

    Args:
        model_path: Optional path to IFC model file
        tools: Dictionary of available tools/functions

    Returns:
        Configured Python interpreter object
    """
    try:
        from code import InteractiveInterpreter

        # Create interpreter with empty globals
        interpreter_globals = {}

        # Add path_ifc_model if provided
        if model_path:
            interpreter_globals['path_ifc_model'] = model_path

        # Add tools to interpreter namespace
        if tools:
            interpreter_globals.update(tools)

        # Create interpreter
        interpreter = InteractiveInterpreter(interpreter_globals)

        logger.debug(f"Interpreter setup with {len(tools) if tools else 0} tools")
        logger.debug(tool for tool in tools or [])
        if model_path:
            logger.debug(f"Model path set: {model_path}")

        return interpreter

    except Exception as e:
        logger.error(f"Failed to setup interpreter: {e}")
        raise


def execute_python(
    python_code: str,
    tools: Dict[str, Callable],
    model_path: Optional[str] = None,
    max_tokens: int = 2048,
    interpreter: Optional[Any] = None,
) -> str:
    """
    Execute Python code and return output.

    Args:
        python_code: Python code to execute
        tools: Dictionary of available tools/functions
        model_path: Optional path to IFC model file
        max_tokens: Maximum number of tokens in output (default: 2048)
        interpreter: Optional existing interpreter to reuse (skips setup_interpreter if provided)

    Returns:
        String output from code execution (truncated if exceeds max_tokens)
    """
    try:
        # Use provided interpreter or create a new one
        if interpreter is None:
            interpreter = setup_interpreter(model_path, tools)
        assert interpreter is not None

        # Capture stdout and stderr
        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()

        # Execute code with output capture
        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            try:
                # Try to compile first to catch syntax errors
                compiled = compile(python_code, '<string>', 'exec')
                interpreter.runcode(compiled)
            except SyntaxError as e:
                return f"Syntax Error: {e}"
            except Exception as e:
                return f"Runtime Error: {e}"

        # Get output
        stdout_output = stdout_buffer.getvalue()
        stderr_output = stderr_buffer.getvalue()

        # Combine outputs
        if stdout_output and stderr_output:
            result = f"STDOUT:\n{stdout_output}\nSTDERR:\n{stderr_output}"
        elif stdout_output:
            result = stdout_output
        elif stderr_output:
            result = f"STDERR:\n{stderr_output}"
        else:
            result = "Code executed successfully (no output)"

        result = result.strip()

        # Truncate output if it exceeds max_tokens
        result = truncate_to_tokens(result, max_tokens)

        logger.debug(f"Python execution completed. Output length: {len(result)}")

        logger.info(f"Output: {result[:50]}...")
        return result

    except Exception as e:
        error_msg = f"Failed to execute Python code: {e}"
        logger.error(error_msg)
        return error_msg


def execute_python_safe(
    python_code: str,
    tools: Dict[str, Callable],
    model_path: Optional[str] = None,
    timeout_seconds: int = 30,
    max_tokens: int = 2048,
    interpreter: Optional[Any] = None,
) -> str:
    """
    Execute Python code with timeout protection.

    Args:
        python_code: Python code to execute
        tools: Dictionary of available tools/functions
        model_path: Optional path to IFC model file
        timeout_seconds: Maximum execution time in seconds
        max_tokens: Maximum number of tokens in output (default: 2048)
        interpreter: Optional existing interpreter to reuse

    Returns:
        String output from code execution or timeout message
    """
    import threading

    result_container: Dict[str, Any] = {"result": None, "completed": False}

    def target():
        try:
            result_container["result"] = execute_python(python_code, tools, model_path, max_tokens, interpreter)
            result_container["completed"] = True
        except Exception as e:
            result_container["result"] = f"Execution failed: {e}"
            result_container["completed"] = True

    # Start thread
    thread = threading.Thread(target=target)
    thread.daemon = True
    thread.start()

    # Wait for completion or timeout
    thread.join(timeout_seconds)

    if not result_container["completed"]:
        return f"Execution timed out after {timeout_seconds} seconds"

    result = result_container["result"]
    return result if isinstance(result, str) else str(result)
