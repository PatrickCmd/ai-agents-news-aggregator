"""Logging configuration for the application."""

import os
import sys
from loguru import logger

# Get log level from environment variable, default to INFO
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Remove default handler
logger.remove()

# Add custom handler with format
logger.add(
    sys.stderr,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level=LOG_LEVEL,
    colorize=True,
)

# Optional: Add file handler
# logger.add(
#     "logs/app.log",
#     rotation="500 MB",
#     retention="10 days",
#     level="DEBUG",
# )


def get_logger(name: str):
    """Get a logger instance with the given name."""
    return logger.bind(name=name)