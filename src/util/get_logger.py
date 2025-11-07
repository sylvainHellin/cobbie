import logging
from logging import Logger
from typing import Literal

from src.config import LOG_LEVEL


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for different log levels."""

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[37m",  # White
        "WARNING": "\033[33m",  # Yellow/Orange
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[91m",  # Bright Red
        "RESET": "\033[0m",  # Reset color
    }

    def format(self, record):
        # Get the original formatted message
        log_message = super().format(record)

        # Add color based on log level
        if record.levelname in self.COLORS:
            color = self.COLORS[record.levelname]
            reset = self.COLORS["RESET"]
            return f"{color}{log_message}{reset}"

        return log_message


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
        # Console handler with colored output
        stream_handler = logging.StreamHandler()
        colored_formatter = ColoredFormatter(
            "%(asctime)s : %(levelname)s : %(name)s : %(message)s"
        )
        stream_handler.setFormatter(colored_formatter)
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
