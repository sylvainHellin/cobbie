"""Loguru logger configuration."""

import sys
from pathlib import Path

from loguru import logger

from src.config import LOG_LEVEL, ROOT_PATH


def setup_logger():
    """Configure loguru with console and rotating file output.

    Sets up two handlers:
    1. Console (stderr) with colored output
    2. Rotating file handler in logs/acc.log (10 MB rotation, 5 files retained)

    The logger respects the LOG_LEVEL setting from src/config.py.
    """
    logger.remove()

    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{file.name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=LOG_LEVEL,
        colorize=True,
    )

    log_dir = Path(ROOT_PATH) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.add(
        log_dir / "acc.log",
        rotation="10 MB",  # Rotate when file reaches 10MB
        retention=5,  # Keep 5 rotated files
        level=LOG_LEVEL,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {file.name}:{function}:{line} - {message}",
    )

    return logger
