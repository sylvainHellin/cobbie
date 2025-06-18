from typing import Literal
import logging
import os

SRC_PATH = os.getenv("SRC_PATH", "")


def get_logger(
    name: str = __name__,
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "DEBUG",
):
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
        logs_dir = os.path.join(SRC_PATH, "logs")

        # Ensure logs directory exists
        os.makedirs(logs_dir, exist_ok=True)

        log_file_path = os.path.join(logs_dir, "logs.log")
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
