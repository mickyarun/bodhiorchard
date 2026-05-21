# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""Regression guard: no ``event=`` kwarg in webhook handler log calls.

structlog reserves the ``event`` key for the log event name (the first
positional arg). Passing it again as a kwarg crashes the runtime with
``BoundLogger.info() got multiple values for argument 'event'`` —
which surfaces as a 500 on the affected GitHub webhook delivery and
the webhook just retries forever.

Production hit this twice on the ``review_author_unresolved`` log call
in ``_handle_review_submitted``. Once was a fix; twice means a
regression guard. This test scans every ``logger.<level>(...)`` call in
``github_webhook_handler`` and asserts none of them pass ``event=`` as
a kwarg — the bare-``event`` antipattern can't sneak back in.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_HANDLER_PATH = (
    Path(__file__).resolve().parents[2] / "app" / "services" / "github_webhook_handler.py"
)

_LOG_METHODS = {"info", "warning", "error", "debug", "exception", "critical"}


def _logger_calls_with_event_kwarg(source: str) -> list[tuple[int, str]]:
    """Return ``[(lineno, code_snippet)]`` for every ``logger.X(event=...)`` call."""
    tree = ast.parse(source)
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Match ``logger.<method>(...)`` shape; allow any name on the
        # left so re-aliased loggers are still caught.
        if not isinstance(func, ast.Attribute) or func.attr not in _LOG_METHODS:
            continue
        for kw in node.keywords:
            if kw.arg == "event":
                hits.append((node.lineno, ast.unparse(node)))
                break
    return hits


def test_no_event_kwarg_in_webhook_logger_calls() -> None:
    source = _HANDLER_PATH.read_text(encoding="utf-8")
    hits = _logger_calls_with_event_kwarg(source)
    if hits:
        formatted = "\n".join(f"  L{ln}: {snippet[:120]}" for ln, snippet in hits)
        pytest.fail(
            "github_webhook_handler.py uses ``event=`` as a logger kwarg — "
            "this collides with structlog's reserved event key and 500s the "
            "webhook at runtime. Rename to a domain-specific key "
            "(e.g. ``webhook_event=``).\n\n" + formatted
        )


def test_detector_catches_the_old_bug_pattern() -> None:
    # Self-check: the AST walker actually fires on the historical bug
    # shape, otherwise a green ``test_no_event_kwarg_...`` could be
    # falsely reassuring.
    bad = """
import structlog
logger = structlog.get_logger(__name__)

def f():
    logger.info("event_name", event="reserved", x=1)
"""
    hits = _logger_calls_with_event_kwarg(bad)
    assert len(hits) == 1
    assert "event='reserved'" in hits[0][1].replace('"', "'")
