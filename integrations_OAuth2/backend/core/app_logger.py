import logging
import os
import sys
from pythonjsonlogger import jsonlogger

def get_logger(name: str) -> logging.Logger:
    """
    Configures and returns a production-grade logger.

    - Reads log level from `LOG_LEVEL` environment variable (default: INFO).
    - Outputs logs in a structured JSON format.
    - Includes standard fields like timestamp, level, name, and message.
    """
    # 1. Create a logger
    logger = logging.getLogger(name)

    # 2. Set log level from environment variable, defaulting to INFO
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logger.setLevel(log_level)

    # 3. Prevent logs from being propagated to the root logger
    logger.propagate = False

    # 4. Create a handler to stream logs to standard output
    log_handler = logging.StreamHandler(sys.stdout)

    # 5. Define the JSON format and add it to the handler
    formatter = jsonlogger.JsonFormatter("%(asctime)s %(name)s %(levelname)s %(message)s")
    log_handler.setFormatter(formatter)

    # 6. Add the handler to the logger, but only if it doesn't have handlers already
    if not logger.handlers:
        logger.addHandler(log_handler)

    return logger
