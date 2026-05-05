# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Tests for ``app.services.scan_checkpoints`` — error classification + publish dedup.

Wrapper / ``run_checkpointed_phase`` behaviour is covered in the sibling
``test_scan_checkpoints_wrapper.py`` so each file stays focused and
under the project's 400-line gate.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from app.models.scan_phase import ScanErrorCode
from app.services import scan_checkpoints as sc

# ───────────────────────── classify_scan_error ─────────────────────────


@pytest.mark.parametrize(
    ("exc_factory", "expected_code"),
    [
        (lambda: sc.MaxTurnsError("num_turns=41 max=40"), ScanErrorCode.MAX_TURNS),
        (
            lambda: sc.ClaudeSubprocessError("returncode=1"),
            ScanErrorCode.CLAUDE_SUBPROCESS,
        ),
        (lambda: sc.MCPError("write_feature_registry failed"), ScanErrorCode.MCP_ERROR),
        (lambda: sc.PhaseTimeoutError("deadline exceeded"), ScanErrorCode.TIMEOUT),
        (lambda: sc.OrphanFeaturesError("3 orphans"), ScanErrorCode.ORPHAN_FEATURE),
        (lambda: TimeoutError("socket"), ScanErrorCode.TIMEOUT),
        (lambda: ValueError("boom"), ScanErrorCode.EXCEPTION),
    ],
)
def test_classify_scan_error_codes(exc_factory, expected_code) -> None:
    """Every typed subclass + builtin timeout + bare exception classifies correctly."""
    exc = exc_factory()
    code, message = sc.classify_scan_error(exc)
    assert code is expected_code
    assert message != ""


def test_classify_scan_error_empty_uses_class_name() -> None:
    """When ``str(exc)`` is empty, classifier falls back to the class name
    so the ``error_message`` column is never blank."""
    code, message = sc.classify_scan_error(RuntimeError())
    assert code is ScanErrorCode.EXCEPTION
    assert message == "RuntimeError"


def test_classify_scan_error_truncates_long_messages() -> None:
    """Messages longer than 2000 chars are truncated with a marker so
    the ``error_message`` column can't be blown up by a huge traceback."""
    code, message = sc.classify_scan_error(RuntimeError("x" * 5000))
    assert code is ScanErrorCode.EXCEPTION
    assert len(message) == 2000
    assert message.endswith("...")


# ───────────────────────── publish_scan_status dedup ─────────────────────────


@pytest.fixture(autouse=True)
def _reset_publish_dedup() -> None:
    """Isolate the module-level dedup cache between tests."""
    sc._last_publish_digest.clear()
    yield
    sc._last_publish_digest.clear()


async def test_publish_dedup_suppresses_identical_snapshot() -> None:
    """Two identical publishes for the same scan → only one hits the sink."""
    scan_id = uuid.uuid4()
    snapshot = {
        "status": "running",
        "progress": 40,
        "phases": [{"phase": "B", "status": "done"}],
    }
    published: list[tuple[str, dict[str, Any]]] = []

    def sink(topic: str, payload: dict[str, Any]) -> None:
        published.append((topic, payload))

    first = await sc.publish_scan_status(scan_id, snapshot, publisher=sink)
    second = await sc.publish_scan_status(scan_id, dict(snapshot), publisher=sink)

    assert first is True
    assert second is False
    assert len(published) == 1
    assert published[0][0] == f"scan:{scan_id}"


async def test_publish_fires_on_state_transition() -> None:
    """A different snapshot (even one byte) must publish again."""
    scan_id = uuid.uuid4()
    published: list[tuple[str, dict[str, Any]]] = []

    def sink(topic: str, payload: dict[str, Any]) -> None:
        published.append((topic, payload))

    await sc.publish_scan_status(scan_id, {"status": "running", "progress": 40}, publisher=sink)
    await sc.publish_scan_status(scan_id, {"status": "running", "progress": 50}, publisher=sink)

    assert len(published) == 2


async def test_publish_dedup_scoped_per_scan() -> None:
    """Different scan_ids dedup independently — one scan's digest must
    never suppress another scan's publish."""
    scan_a, scan_b = uuid.uuid4(), uuid.uuid4()
    snapshot = {"status": "running", "progress": 40}
    published: list[str] = []

    def sink(topic: str, payload: dict[str, Any]) -> None:
        published.append(topic)

    await sc.publish_scan_status(scan_a, snapshot, publisher=sink)
    await sc.publish_scan_status(scan_b, snapshot, publisher=sink)

    assert published == [f"scan:{scan_a}", f"scan:{scan_b}"]


async def test_clear_scan_publish_dedup_resets_digest() -> None:
    """After clearing, a republish of the same snapshot must fire again."""
    scan_id = uuid.uuid4()
    published: list[str] = []

    def sink(topic: str, payload: dict[str, Any]) -> None:
        published.append(topic)

    snapshot = {"status": "completed"}
    await sc.publish_scan_status(scan_id, snapshot, publisher=sink)
    sc.clear_scan_publish_dedup(scan_id)
    await sc.publish_scan_status(scan_id, snapshot, publisher=sink)

    assert len(published) == 2
