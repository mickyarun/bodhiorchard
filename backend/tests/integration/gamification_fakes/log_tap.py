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

"""Fail a test when a gamification rule swallowed an error.

Every skill-point, streak and quiz leg catches its own exceptions and logs a
``*_failed`` warning, so "nobody was paid" could also mean "the rule
crashed". :func:`failure_log_tap` wraps each of those modules' ``logger`` for
one test, records every warning, error or exception whose event ends in
``_failed``, and fails the test at teardown unless the test allowed it.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import ModuleType
from typing import Any

import pytest

from app.services import (
    code_review_sp,
    dev_quality_sp,
    quiz_batch_generation,
    quiz_monthly_rollup,
    quiz_notify,
    quiz_persist,
    quiz_scheduler,
    sp_attribution,
    sp_designer,
    sp_developer,
    sp_pm,
    sp_qa,
    sp_service,
    sp_split,
    sp_tech_arch,
    stage_award,
    xp_service,
)

TAPPED: tuple[ModuleType, ...] = (
    code_review_sp,
    dev_quality_sp,
    quiz_batch_generation,
    quiz_monthly_rollup,
    quiz_notify,
    quiz_persist,
    quiz_scheduler,
    sp_attribution,
    sp_designer,
    sp_developer,
    sp_pm,
    sp_qa,
    sp_service,
    sp_split,
    sp_tech_arch,
    stage_award,
    xp_service,
)
_LEVELS = frozenset({"warning", "error", "exception", "critical"})


class LogTap:
    """The ``*_failed`` events logged during one test, and the ones it expects."""

    def __init__(self) -> None:
        self.failures: list[str] = []
        self.allowed: set[str] = set()

    def allow(self, event: str) -> None:
        """Declare that this test expects ``event`` to be logged."""
        self.allowed.add(event)

    def unexpected(self) -> list[str]:
        """Failure events the test did not allow."""
        return [event for event in self.failures if event not in self.allowed]


class _TappedLogger:
    """Delegates to the real logger, noting ``*_failed`` events on the way."""

    def __init__(self, inner: Any, tap: LogTap) -> None:
        self._inner = inner
        self._tap = tap

    def __getattr__(self, name: str) -> Any:
        method = getattr(self._inner, name)
        if name not in _LEVELS:
            return method

        def record(event: str, *args: Any, **kwargs: Any) -> Any:
            if event.endswith("_failed"):
                self._tap.failures.append(event)
            return method(event, *args, **kwargs)

        return record


@pytest.fixture(autouse=True)
def failure_log_tap(monkeypatch: pytest.MonkeyPatch) -> Iterator[LogTap]:
    """Tap the gamification loggers; fail on any ``*_failed`` event not allowed."""
    tap = LogTap()
    for module in TAPPED:
        monkeypatch.setattr(module, "logger", _TappedLogger(module.logger, tap))
    yield tap
    unexpected = tap.unexpected()
    if unexpected:
        pytest.fail(f"a rule swallowed an error: {unexpected}", pytrace=False)
