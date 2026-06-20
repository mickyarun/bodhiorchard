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

"""Tests for the PM requirement-credit taper."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.sp_pm import _requirement_amount, award_pm_sp_on_close


def _learning(estimated: float | None, cycle: float | None, drift: float | None = None):
    metrics = {"phase_metrics": {"tech_arch": {"drift_pct": drift}}} if drift is not None else {}
    return SimpleNamespace(estimated_days=estimated, cycle_time_days=cycle, metrics=metrics)


def test_requirement_full_when_on_estimate() -> None:
    assert _requirement_amount(_learning(10.0, 10.0)) == 1.0
    assert _requirement_amount(_learning(10.0, 8.0)) == 1.0  # under estimate


def test_requirement_full_when_no_estimate_data() -> None:
    assert _requirement_amount(None) == 1.0
    assert _requirement_amount(_learning(None, 10.0)) == 1.0
    assert _requirement_amount(_learning(10.0, None)) == 1.0


def test_requirement_halved_above_30pct_overrun() -> None:
    # 40% over → half credit
    assert _requirement_amount(_learning(10.0, 14.0)) == 0.5


def test_requirement_zero_above_50pct_overrun() -> None:
    # 60% over → no credit
    assert _requirement_amount(_learning(10.0, 16.0)) == 0.0


def test_requirement_boundary_at_30_is_full() -> None:
    # exactly 30% over is NOT > 30 → still full
    assert _requirement_amount(_learning(10.0, 13.0)) == 1.0


@pytest.mark.asyncio
async def test_awarder_swallows_setup_failure() -> None:
    """A failing setup read must not escape (on_bud_closed contract)."""
    repo = MagicMock()
    repo.first_status_change_to = AsyncMock(side_effect=RuntimeError("db hiccup"))
    bud = SimpleNamespace(id=uuid.uuid4(), bud_number=1)

    with patch("app.services.sp_pm.BUDTimelineRepository", return_value=repo):
        # Must not raise.
        await award_pm_sp_on_close(MagicMock(), uuid.uuid4(), bud)
