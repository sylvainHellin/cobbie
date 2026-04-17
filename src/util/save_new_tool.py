import os

from loguru import logger


def save_new_tool(
    function_name: str,
    function_implementation: str,
    directory_path: str,
) -> bool:
    """Save a generated function as `{directory_path}/{function_name}.py`."""
    file_path = os.path.join(directory_path, f"{function_name}.py")
    with open(file_path, "w") as file:
        file.write(function_implementation)
    logger.info(f"New function saved to {file_path}")
    return True
