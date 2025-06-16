from typing import Literal
import logging


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
        logging.Logger: A configured logger instance with a stream handler and formatter.
    """
    logger = logging.getLogger(name)
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s : %(levelname)s : %(name)s : %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

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
