import os
from typing import Optional
from src.config import CREATED_TOOLS_PATH, LOG_LEVEL
from src.engine.util import get_logger

logger = get_logger(name="save_new_function", log_level=LOG_LEVEL)

def save_new_tool(function_name: str, function_implementation: str, directory_path:Optional[str] = None)->bool:
    """
    Save the provided function code as a file named according to the provided function_name to the new_file_path. If no path is provided, will use the default location for created tools from the config file.
    """
    tool_directory = directory_path or CREATED_TOOLS_PATH
    file_path = os.path.join(tool_directory, f"{function_name}.py")
    with open(file=file_path, mode="w") as file:
        file.write(function_implementation)
        logger.info(f"New function saved to {file_path}")
        return True
