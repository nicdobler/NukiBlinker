"""Tests for application logging configuration (#115)."""

import logging

import pytest

from nukiblinker.logging_config import (
    _FILE_HANDLER_NAME,
    add_file_logging,
    setup_logging,
)


@pytest.fixture
def clean_root_logger():
    """Snapshot and restore the root logger handlers around each test."""
    root = logging.getLogger()
    saved = list(root.handlers)
    saved_level = root.level
    yield root
    for h in list(root.handlers):
        if h not in saved:
            root.removeHandler(h)
            h.close()
    for h in saved:
        if h not in root.handlers:
            root.addHandler(h)
    root.setLevel(saved_level)


def _file_handlers(root):
    return [h for h in root.handlers if getattr(h, "name", None) == _FILE_HANDLER_NAME]


def test_add_file_logging_writes_to_file(clean_root_logger, tmp_path):
    """A configured file path attaches a rotating handler and records logs."""
    log_path = tmp_path / "logs" / "nukiblinker.log"
    setup_logging("INFO")
    add_file_logging(str(log_path), level="INFO")

    logging.getLogger("nukiblinker.test").info("hello-file-log")

    assert log_path.exists()
    assert "hello-file-log" in log_path.read_text(encoding="utf-8")


def test_add_file_logging_creates_parent_dir(clean_root_logger, tmp_path):
    """The parent directory (the mounted logs/ volume) is created if missing."""
    log_path = tmp_path / "deep" / "nested" / "app.log"
    add_file_logging(str(log_path))
    assert log_path.parent.is_dir()


def test_add_file_logging_is_idempotent(clean_root_logger, tmp_path):
    """Calling twice must not stack duplicate file handlers."""
    log_path = tmp_path / "app.log"
    add_file_logging(str(log_path))
    add_file_logging(str(log_path))
    assert len(_file_handlers(clean_root_logger)) == 1


def test_add_file_logging_empty_path_disables(clean_root_logger):
    """An empty file path leaves no file handler attached."""
    add_file_logging("")
    assert _file_handlers(clean_root_logger) == []


def test_add_file_logging_uses_timed_rotation(clean_root_logger, tmp_path):
    """The handler is a TimedRotatingFileHandler with the requested schedule."""
    from logging.handlers import TimedRotatingFileHandler

    log_path = tmp_path / "app.log"
    add_file_logging(str(log_path), when="W0", backup_count=4)
    handlers = _file_handlers(clean_root_logger)
    assert len(handlers) == 1
    assert isinstance(handlers[0], TimedRotatingFileHandler)
    assert handlers[0].backupCount == 4
