"""Import all available tools"""

import importlib
import inspect
import os
from typing import Callable, Dict, List

from src.config import CREATED_TOOLS_PATH
from src.engine.util.get_logger import get_logger

logger = get_logger(__name__)


# Import all functions from each file
def get_created_tools(tools: List[Callable] = []) -> Dict[str, Callable]:
    """
    Return a Dict[str, Callable] with all the name and functions from:
    - the provided tools parameter
    - the functions in the tools/created directory
    """

    # Get all Python files in the directory (excluding __init__.py)
    python_files = [
        f[:-3]
        for f in os.listdir(CREATED_TOOLS_PATH)
        if f.endswith(".py") and f != "__init__.py"
    ]
    fn_dict: Dict[str, Callable] = {}

    for fn in tools:
        fn_dict[fn.__name__] = fn

    for module_name in python_files:
        try:
            # Use absolute import path
            module = importlib.import_module(f"src.engine.tools.created.{module_name}")
            # Get all objects from the module
            for name, fn in inspect.getmembers(module):
                # Only include functions that are defined in this module (not imported)
                # and exclude built-in types, classes, etc.
                if (
                    inspect.isfunction(fn)
                    and fn.__module__ == module.__name__
                    and not name.startswith("_")
                ):
                    globals()[name] = fn
                    fn_dict[name] = fn
        except Exception as e:
            file_path = os.path.join(CREATED_TOOLS_PATH, f"{module_name}.py")
            logger.warning(
                f"Could not import module '{module_name}'. Deleting it. Error: {e}"
            )
            try:
                os.remove(file_path)
                logger.info(f"Successfully deleted problematic tool file: {file_path}")
            except OSError as remove_error:
                logger.error(f"Error deleting file {file_path}: {remove_error}")
            continue

    return fn_dict


def get_tools_description(tools: Dict[str, Callable] = {}) -> str:
    """Returns a serialised list of existing tools, along with their descriptions."""
    tools = tools or get_created_tools()
    tools_description = ""
    for fn_name, fn in tools.items():
        docstring = getattr(fn, "__doc__", "No description available.")
        # Clean up the docstring formatting and remove code blocks
        docstring_lines = []
        in_code_block = False
        for line in docstring.strip().split("\n"):
            line = line.strip()
            # Skip code block markers and content
            if line.startswith("```"):
                in_code_block = not in_code_block
                continue
            if not in_code_block:
                docstring_lines.append(line)

        docstring = " ".join(docstring_lines)
        tools_description += f"\n- `{fn_name}`: {docstring}"

    return tools_description


def get_tools_names(tools: Dict[str, Callable] = {}) -> str:
    """Returns a serialized list of existing tools names."""
    tools = tools or get_created_tools()
    tool_names = [fn_name for (fn_name, fn) in tools.items()]
    return ", ".join(tool_names)


if __name__ == "__main__":
    tools = get_created_tools()
    for name, fn in tools.items():
        # print(f"function's name: {name}\nfunction's docstring: {fn.__doc__}\n---\n")
        logger.info(f"function name: {name}")

    logger.info("/n/n")
    tools_description = get_tools_description()
    logger.info(tools_description)

    logger.info(get_tools_names())
