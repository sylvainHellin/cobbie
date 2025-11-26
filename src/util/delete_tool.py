"""Delete tools from filesystem and database."""

from pathlib import Path

from src.config import CREATED_TOOLS_PATH, LOG_LEVEL
from src.util.get_logger import get_logger
from src.db.query import delete_tool_from_db

logger = get_logger(name="delete_tool", log_level=LOG_LEVEL)


def delete_tool(tool_name: str) -> bool:
    """
    Delete tool from filesystem and database.

    Returns:
        True if successful, False otherwise
    """
    try:
        # Delete file
        file_path = Path(CREATED_TOOLS_PATH) / f"{tool_name}.py"
        if file_path.exists():
            file_path.unlink()
            logger.info(f"Deleted tool file: {file_path}")

        # Delete metadata
        delete_tool_from_db(tool_name)
        logger.info(f"Deleted tool metadata: {tool_name}")

        return True

    except Exception as e:
        logger.error(f"Error deleting tool {tool_name}: {e}")
        return False
