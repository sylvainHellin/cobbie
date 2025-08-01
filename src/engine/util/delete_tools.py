import os
from typing import Optional
from src.config import CREATED_TOOLS_PATH, LOG_LEVEL
from src.engine.util import get_logger

logger = get_logger(name="delete_tools", log_level=LOG_LEVEL)


def delete_tools(
    first_function_name: str,
    second_function_name: str,
    directory_path: Optional[str] = None,
) -> bool:
    """
    Delete two tool files based on their function names from the specified directory.
    If no directory path is provided, will use the default location for created tools from the config file.

    Args:
        tool_name_1: Name of the first tool/function to delete
        tool_name_2: Name of the second tool/function to delete
        directory_path: Optional custom directory path. If None, uses CREATED_TOOLS_PATH

    Returns:
        bool: True if both files were successfully deleted, False otherwise
    """
    tool_directory = directory_path or CREATED_TOOLS_PATH

    file_path_1 = os.path.join(tool_directory, f"{first_function_name}.py")
    file_path_2 = os.path.join(tool_directory, f"{second_function_name}.py")

    success = True

    # Delete first tool file
    try:
        if os.path.exists(file_path_1):
            os.remove(file_path_1)
            logger.info(f"Tool file deleted: {file_path_1}")
        else:
            logger.warning(f"Tool file not found: {file_path_1}")
            success = False
    except Exception as e:
        logger.error(f"Failed to delete {file_path_1}: {e}")
        success = False

    # Delete second tool file
    try:
        if os.path.exists(file_path_2):
            os.remove(file_path_2)
            logger.info(f"Tool file deleted: {file_path_2}")
        else:
            logger.warning(f"Tool file not found: {file_path_2}")
            success = False
    except Exception as e:
        logger.error(f"Failed to delete {file_path_2}: {e}")
        success = False

    return success
