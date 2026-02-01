"""Loguru logger configuration for the Cobbie system.

This module provides centralized logging configuration using loguru,
replacing the custom ColoredFormatter-based logging system.
"""

import sys
from pathlib import Path

from loguru import logger

from src.config import LOG_LEVEL, ROOT_PATH


def setup_logger():
    """Configure loguru with console and rotating file output.

    Sets up two handlers:
    1. Console (stderr) with colored output
    2. Rotating file handler in src/db/logs/cobbie.log

    The logger respects the LOG_LEVEL setting from src/config.py.
    File rotation occurs at 10 MB with retention of 5 files (~50 MB total).

    Returns:
        logger: Configured loguru logger instance
    """
    # Remove default handler
    logger.remove()

    # Console handler with colors and detailed formatting
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{file.name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=LOG_LEVEL,
        colorize=True,
    )

    # File handler with rotation
    log_dir = Path(ROOT_PATH) / "src" / "db" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.add(
        log_dir / "cobbie.log",
        rotation="10 MB",  # Rotate when file reaches 10MB
        retention=5,  # Keep 5 rotated files
        level=LOG_LEVEL,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {file.name}:{function}:{line} - {message}",
    )

    return logger
