"""Import all available tools"""

import importlib
import inspect
import os
from typing import Callable, Dict, List

from src.config import CREATED_TOOLS_PATH


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
        except ImportError as e:
            print(f"Warning: Could not import module {module_name}: {e}")
            continue

    return fn_dict


if __name__ == "__main__":
    tools = get_created_tools()
    for name, fn in tools.items():
        # print(f"function's name: {name}\nfunction's docstring: {fn.__doc__}\n---\n")
        print(f"function name: {name}")
