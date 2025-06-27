import logging
import os
from logging import Logger
from typing import Literal

from src.config import LOG_LEVEL, ROOT_PATH

# Append last_log.log to logs.log and clear it when the module is imported
logs_dir = os.path.join(ROOT_PATH, "src/experiment/logs")
log_file_path = os.path.join(logs_dir, "last_log.log")
history_log_path = os.path.join(logs_dir, "logs.log")

# Ensure logs directory exists
os.makedirs(logs_dir, exist_ok=True)

# Append last_log.log content to logs.log before clearing it
if os.path.exists(log_file_path):
    with open(log_file_path, "r") as last_log_file:
        content = last_log_file.read()
        if content.strip():  # Only append if there's actual content
            with open(history_log_path, "a") as history_log_file:
                history_log_file.write(content)
                # Add a separator between different experiment logs
                history_log_file.write("\n" + "=" * 80 + "\n\n")

    # Clear the last_log.log file
    open(log_file_path, "w").close()


def get_logger(
    name: str = __name__,
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = LOG_LEVEL,
) -> Logger:
    """Configure and return a logger with the specified name and log level.

    Args:
        name (str, optional): The name of the logger. Defaults to __name__.
        log_level (Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"], optional):
            The logging level to set. Defaults to "DEBUG".

    Returns:
        logging.Logger: A configured logger instance with both stream and file handlers.
    """
    logger = logging.getLogger(name)

    # Only add handlers if none exist
    if not logger.handlers:
        # Console handler
        stream_handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s : %(levelname)s : %(name)s : %(message)s"
        )
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

        # File handler
        log_file_path = os.path.join(logs_dir, "last_log.log")
        file_handler = logging.FileHandler(log_file_path)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    if log_level == "CRITICAL":
        logger.setLevel(logging.CRITICAL)
    elif log_level == "ERROR":
        logger.setLevel(logging.ERROR)
    elif log_level == "WARNING":
        logger.setLevel(logging.WARNING)
    elif log_level == "INFO":
        logger.setLevel(logging.INFO)
    else:
        logger.setLevel(logging.DEBUG)

    return logger
