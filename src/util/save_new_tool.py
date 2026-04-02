import os
from typing import Optional

from loguru import logger

from src.config import CREATED_TOOLS_PATH


def save_new_tool(function_name: str, function_implementation: str, directory_path: Optional[str] = None, global_question_num: Optional[int] = None) -> bool:
    """
    Save the provided function code as a file named according to the provided function_name to the new_file_path. If no path is provided, will use the default location for created tools from the config file.

    Args:
        function_name: Name of the function to save
        function_implementation: Source code of the function
        directory_path: Optional custom directory path
        global_question_num: Unused (kept for API compatibility)

    Returns:
        True if save succeeded, False otherwise
    """
    tool_directory = directory_path or CREATED_TOOLS_PATH
    file_path = os.path.join(tool_directory, f"{function_name}.py")
    with open(file=file_path, mode="w") as file:
        file.write(function_implementation)
        logger.info(f"New function saved to {file_path}")
        return True
