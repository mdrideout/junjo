import sys

from loguru import logger


def setup_logging():
    # Remove the default logger
    logger.remove()

    # Define the log format
    logger_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    # Add stderr logging (for Docker environments)
    logger.add(
        sys.stderr,
        level="DEBUG",
        colorize=True,
        format=logger_format,
    )

    # Add file logging
    logger.add("logs/backend.log", rotation="10 MB", level="DEBUG")
