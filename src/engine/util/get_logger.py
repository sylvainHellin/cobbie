import logging
from logging import Logger
from typing import Literal

from src.config import LOG_LEVEL


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
