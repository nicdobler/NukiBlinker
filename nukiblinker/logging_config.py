"""Structured logging configuration for NukiBlinker."""

import logging
import sys


LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with console handler."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(numeric_level)

    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(numeric_level)
        handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
        root.addHandler(handler)

    # Silence chatty third-party libraries
    for lib in ("httpx", "httpcore", "pychromecast", "zeroconf", "casttube", "pyatv"):
        logging.getLogger(lib).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a logger scoped to the given module name."""
    return logging.getLogger(f"nukiblinker.{name}")
