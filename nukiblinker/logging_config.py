"""Structured logging configuration for NukiBlinker."""

import logging
import logging.handlers
import sys
from pathlib import Path


LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S%z"  # Include timezone offset (#162)

# Marker so add_file_logging is idempotent (avoid duplicate file handlers).
_FILE_HANDLER_NAME = "nukiblinker_file"


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
    for lib in ("httpx", "httpcore", "pychromecast", "zeroconf", "casttube"):
        logging.getLogger(lib).setLevel(logging.WARNING)


def add_file_logging(file_path: str, when: str = "W0", backup_count: int = 4,
                     level: str = "INFO") -> None:
    """Add a rotating file handler to the root logger (#115).

    The app log is written to ``file_path`` (under the mounted ``logs/`` volume)
    in addition to the console. The file rotates on the ``when`` schedule
    (default ``W0`` — weekly, Monday) and keeps ``backup_count`` old files for
    basic housekeeping. An empty ``file_path`` disables file logging. Safe to
    call more than once: an existing NukiBlinker file handler is replaced.

    Called after the config is loaded (``setup_logging`` runs earlier for the
    console, before the config file is read).
    """
    if not file_path:
        return

    root = logging.getLogger()
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Remove a previously-added file handler so repeated calls don't stack up.
    for existing in list(root.handlers):
        if getattr(existing, "name", None) == _FILE_HANDLER_NAME:
            root.removeHandler(existing)
            existing.close()

    path = Path(file_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.TimedRotatingFileHandler(
            str(path), when=when, backupCount=backup_count, encoding="utf-8"
        )
    except OSError as e:
        logging.getLogger("nukiblinker.logging").warning(
            "Could not open log file %s — file logging disabled: %s", file_path, e
        )
        return

    handler.name = _FILE_HANDLER_NAME
    handler.setLevel(numeric_level)
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    root.addHandler(handler)
    logging.getLogger("nukiblinker.logging").info(
        "File logging enabled: %s (rotation=%s, keep=%d)", file_path, when, backup_count
    )


def get_logger(name: str) -> logging.Logger:
    """Return a logger scoped to the given module name."""
    return logging.getLogger(f"nukiblinker.{name}")
