"""Python execution utilities for COBBIE and other components."""

from typing import Dict, Callable, Optional, Any
import sys
import io
from contextlib import redirect_stdout, redirect_stderr
import logging

logger = logging.getLogger(__name__)


def setup_interpreter(
    model_path: Optional[str] = None,
    tools: Dict[str, Callable] = None
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
        import builtins
        
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
        
        logger.info(f"Interpreter setup with {len(tools) if tools else 0} tools")
        if model_path:
            logger.info(f"Model path set: {model_path}")
            
        return interpreter
        
    except Exception as e:
        logger.error(f"Failed to setup interpreter: {e}")
        raise


def execute_python(
    python_code: str,
    tools: Dict[str, Callable],
    model_path: Optional[str] = None
) -> str:
    """
    Execute Python code and return output.
    
    Args:
        python_code: Python code to execute
        tools: Dictionary of available tools/functions
        model_path: Optional path to IFC model file
        
    Returns:
        String output from code execution
    """
    try:
        # Setup interpreter for this execution
        interpreter = setup_interpreter(model_path, tools)
        
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
            
        logger.debug(f"Python execution completed. Output length: {len(result)}")
        return result.strip()
        
    except Exception as e:
        error_msg = f"Failed to execute Python code: {e}"
        logger.error(error_msg)
        return error_msg


def execute_python_safe(
    python_code: str,
    tools: Dict[str, Callable],
    model_path: Optional[str] = None,
    timeout_seconds: int = 30
) -> str:
    """
    Execute Python code with timeout protection.
    
    Args:
        python_code: Python code to execute
        tools: Dictionary of available tools/functions
        model_path: Optional path to IFC model file
        timeout_seconds: Maximum execution time in seconds
        
    Returns:
        String output from code execution or timeout message
    """
    import signal
    import threading
    
    result_container = {"result": None, "completed": False}
    
    def target():
        try:
            result_container["result"] = execute_python(python_code, tools, model_path)
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
    
    return result_container["result"]