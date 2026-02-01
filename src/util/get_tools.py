"""Generic tool loading utilities for all tool directories."""

import importlib
import inspect
import os
from typing import Callable, Dict, List, Literal

from loguru import logger

from src.config import CREATED_TOOLS_PATH, INITIAL_TOOLS_PATH, MANUAL_TOOLS_PATH

# Map directory names to their paths
TOOL_PATHS = {
    "initial": INITIAL_TOOLS_PATH,
    "created": CREATED_TOOLS_PATH,
    "manual": MANUAL_TOOLS_PATH,
}


def get_tools_from_directory(
    directory: Literal["initial", "created", "manual"],
    allow_deletion: bool = False
) -> Dict[str, Callable]:
    """
    Load tools from specified directory using dynamic module inspection.

    Args:
        directory: Which tool directory to load from ('initial', 'created', or 'manual')
        allow_deletion: If True, delete files that fail to import (created tools only)

    Returns:
        Dictionary mapping function names to callable functions

    Raises:
        ValueError: If directory is not one of the valid options
    """
    if directory not in TOOL_PATHS:
        raise ValueError(f"Invalid directory '{directory}'. Must be one of: {list(TOOL_PATHS.keys())}")

    tool_path = TOOL_PATHS[directory]

    # Check if directory exists
    if not os.path.exists(tool_path):
        logger.warning(f"Tool directory does not exist: {tool_path}")
        return {}

    # Get all Python files in the directory (excluding __init__.py)
    try:
        python_files = [
            f[:-3]
            for f in os.listdir(tool_path)
            if f.endswith(".py") and f != "__init__.py"
        ]
    except OSError as e:
        logger.error(f"Could not list files in {tool_path}: {e}")
        return {}

    fn_dict: Dict[str, Callable] = {}

    for module_name in python_files:
        try:
            # Use absolute import path
            module = importlib.import_module(f"src.tools.{directory}.{module_name}")

            # Get all functions from the module
            for name, fn in inspect.getmembers(module):
                # Only include functions that are:
                # - actual functions (not classes, modules, etc.)
                # - defined in this module (not imported)
                # - public (don't start with underscore)
                if (
                    inspect.isfunction(fn)
                    and fn.__module__ == module.__name__
                    and not name.startswith("_")
                ):
                    fn_dict[name] = fn

        except Exception as e:
            file_path = os.path.join(tool_path, f"{module_name}.py")

            if allow_deletion:
                # For created tools, delete broken files
                logger.warning(
                    f"Could not import module '{module_name}' from {directory}/. Deleting it. Error: {e}"
                )
                try:
                    os.remove(file_path)
                    logger.info(f"Successfully deleted problematic tool file: {file_path}")
                except OSError as remove_error:
                    logger.error(f"Error deleting file {file_path}: {remove_error}")
            else:
                # For initial/manual tools, just log error and preserve file
                logger.error(
                    f"Could not import module '{module_name}' from {directory}/. Keeping file. Error: {e}"
                )
            continue

    logger.debug(f"Loaded {len(fn_dict)} tools from {directory}/: {list(fn_dict.keys())}")
    return fn_dict


def get_tools(
    directories: List[Literal["initial", "created", "manual"]],
    allow_created_deletion: bool = False
) -> Dict[str, Callable]:
    """
    Load tools from multiple directories with duplicate handling.

    Tools are loaded in the order specified. If the same function name appears
    in multiple directories, the version from the later directory wins.

    Args:
        directories: List of directories to load from (processed in order)
        allow_created_deletion: Whether to delete broken created tools

    Returns:
        Combined dictionary of all tools (later directories override earlier)

    Examples:
        # Load only initial tools
        tools = get_tools(['initial'])

        # Load initial and created (default evaluation behavior)
        tools = get_tools(['initial', 'created'], allow_created_deletion=True)

        # Load all tools, with manual overriding created and initial
        tools = get_tools(['initial', 'created', 'manual'])
    """
    if not directories:
        raise ValueError("At least one directory must be specified")

    fn_dict: Dict[str, Callable] = {}
    tool_origins: Dict[str, str] = {}  # Track which directory each tool came from

    for directory in directories:
        # Determine if deletion is allowed for this directory
        allow_deletion = allow_created_deletion and directory == "created"

        # Load tools from this directory
        dir_tools = get_tools_from_directory(directory, allow_deletion=allow_deletion)

        # Check for duplicates and log warnings
        for tool_name, tool_fn in dir_tools.items():
            if tool_name in fn_dict:
                logger.warning(
                    f"Tool '{tool_name}' from '{directory}/' overrides version from '{tool_origins[tool_name]}/'"
                )
            fn_dict[tool_name] = tool_fn
            tool_origins[tool_name] = directory

    logger.info(f"Loaded {len(fn_dict)} total tools from {len(directories)} directories")
    return fn_dict
