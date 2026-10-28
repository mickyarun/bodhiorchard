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

"""A settable clock that stands in for one app module's ``datetime``."""

from __future__ import annotations

from datetime import UTC, datetime, tzinfo
from types import ModuleType
from typing import ClassVar, Self

import pytest


class FrozenClock(datetime):
    """A ``datetime`` whose ``now()`` answers the settable aware ``instant``.

    It is a real ``datetime`` subclass, so constructors and arithmetic in the
    module under test behave as usual; only ``now()`` is frozen.
    """

    instant: ClassVar[datetime] = datetime(2026, 3, 2, 12, 0, tzinfo=UTC)

    @classmethod
    def now(cls, tz: tzinfo | None = None) -> Self:
        """The frozen instant, in ``tz`` like the real ``datetime.now``."""
        return cls.fromtimestamp(cls.instant.timestamp(), tz)

    @classmethod
    def set_local(cls, local: datetime) -> None:
        """Move the clock to an aware local wall time (any zone)."""
        cls.instant = local.astimezone(UTC)


def install_clock(
    monkeypatch: pytest.MonkeyPatch, module: ModuleType, start: datetime
) -> type[FrozenClock]:
    """Swap ``module.datetime`` for the clock, starting at ``start``; both undone at teardown."""
    monkeypatch.setattr(FrozenClock, "instant", start.astimezone(UTC))
    monkeypatch.setattr(module, "datetime", FrozenClock)
    return FrozenClock
