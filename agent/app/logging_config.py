"""
Logging configuration for rMirror Agent.

Sets up both file and console logging with proper formatting.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """
    Set up logging to both file and console.

    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)

    Returns:
        Root logger instance
    """
    # Create logs directory
    log_dir = Path.home() / ".config/rmirror"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "agent.log"

    # Create root logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper()))

    # Remove any existing handlers
    logger.handlers.clear()

    # Create formatters
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    console_formatter = logging.Formatter(
        '%(message)s'
    )

    # File handler - rotating log file (max 10MB, keep 5 backups)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.DEBUG)  # Always log DEBUG to file
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Console handler - only INFO and above
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # Log startup
    logger.info(f"Logging initialized - log file: {log_file}")

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for a specific module.

    Args:
        name: Name of the module (usually __name__)

    Returns:
        Logger instance
    """
    return logging.getLogger(name)
