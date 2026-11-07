"""Small logging setup shared by local and container startup."""
import logging
import os


def configure_logging():
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("werkzeug").setLevel(
        getattr(logging, os.getenv("HTTP_LOG_LEVEL", "WARNING").upper(), logging.WARNING)
    )
