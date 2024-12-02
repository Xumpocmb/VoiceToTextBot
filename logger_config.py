from loguru import logger
import sys


logger.remove()
logger.add(
    sys.stderr,
    format="{time} {level} {file}:{line} {message}",
    level="DEBUG",
)
logger.add(
    "bot.log",
    format="{time} {level} {file}:{line} {message}",
    level="DEBUG",
    rotation="1 MB",
    compression="zip"
)


def get_logger():
    return logger
