from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def default_log_directory() -> Path:
    return Path.home() / ".opencut-pyside" / "logs"


def configure_logging() -> Path:
    log_dir = default_log_directory()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "opencut.log"

    root_logger = logging.getLogger()
    if any(isinstance(handler, RotatingFileHandler) for handler in root_logger.handlers):
        return log_dir

    root_logger.setLevel(logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        filename=log_file,
        maxBytes=1_048_576,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    root_logger.addHandler(stream_handler)
    root_logger.addHandler(file_handler)
    return log_dir
