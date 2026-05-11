# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Structured JSON logging configuration for Bodhiorchard.

Configures structlog to output JSON-formatted logs with timestamps,
log level, logger name, and request correlation context. When
``LOG_DIR`` is set (or defaults to ``backend/logs/``) a rotating file
handler also persists the same lines to disk so a long-running scan
can be debugged after the fact without holding open the terminal that
launched ``uvicorn``.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog

# Bound the on-disk log so a runaway loop can't fill the volume. Five
# rotated files of 20 MB = ~100 MB ceiling per backend instance, which
# is plenty for a multi-day scan investigation and small enough that
# operators don't need a separate retention policy.
_LOG_FILE_MAX_BYTES = 20 * 1024 * 1024
_LOG_FILE_BACKUP_COUNT = 5
_DEFAULT_LOG_DIR = Path(__file__).resolve().parents[2] / "logs"


def setup_logging(log_level: str = "INFO", json_output: bool = True) -> None:
    """Configure structlog for JSON-formatted structured logging.

    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR).
        json_output: If True, output JSON. If False, use colored console output.
    """
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if json_output:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    # ``stdlib.LoggerFactory`` routes every structlog call through the
    # stdlib ``logging`` machinery — so the file handler attached below
    # captures the same lines the console sees. ``PrintLoggerFactory``
    # would write straight to stdout and bypass our handler.
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    _attach_file_handler(level)


def _attach_file_handler(level: int) -> None:
    """Add a rotating file handler so logs persist across terminal sessions.

    Failure to set up the file handler is **never** fatal — falling
    back to stdout-only must not block the API from starting. Disk
    full, permission denied, etc. just emit a single warning.
    """
    log_dir_env = os.environ.get("LOG_DIR")
    log_dir = Path(log_dir_env) if log_dir_env else _DEFAULT_LOG_DIR
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_dir / "bodhi.log",
            maxBytes=_LOG_FILE_MAX_BYTES,
            backupCount=_LOG_FILE_BACKUP_COUNT,
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler.setLevel(level)
        root = logging.getLogger()
        # Avoid double-attaching when uvicorn --reload re-imports the module.
        if not any(
            isinstance(h, RotatingFileHandler)
            and getattr(h, "baseFilename", None) == handler.baseFilename
            for h in root.handlers
        ):
            root.addHandler(handler)
    except OSError as exc:
        logging.getLogger(__name__).warning(
            "log_file_handler_setup_failed path=%s error=%s",
            log_dir,
            exc,
        )
