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

"""Tests for the progress-aware current-phase discount (pure logic).

The two repository queries (``phase_completion``, ``has_merged_for_bud``) are
thin SQL and exercised by the integration suite; here we cover the pure
combine + discount logic that decides how much the current phase shrinks.
"""

from __future__ import annotations

from app.services.estimation_engine import PERTEstimate
from app.services.estimation_progress import (
    CURRENT_PHASE_RESIDUAL,
    combine_progress,
    discounted_pert,
)


def test_combine_all_todos_done() -> None:
    """Every todo complete → fully done, regardless of PR signal."""
    assert combine_progress(completed=8, total=8, has_merged_pr=False) == 1.0


def test_combine_no_progress() -> None:
    """Nothing done and no merged PR → 0.0 (no discount applied)."""
    assert combine_progress(completed=0, total=8, has_merged_pr=False) == 0.0


def test_combine_partial_is_linear() -> None:
    """Half the todos done → 0.5."""
    assert combine_progress(completed=4, total=8, has_merged_pr=False) == 0.5


def test_combine_no_todos_is_zero_not_division_error() -> None:
    """A phase with no todos returns 0.0, not a ZeroDivisionError."""
    assert combine_progress(completed=0, total=0, has_merged_pr=False) == 0.0


def test_merged_pr_dominates_thin_todos() -> None:
    """A merged PR is a strong signal — it beats a low todo ratio."""
    assert combine_progress(completed=1, total=8, has_merged_pr=True) == 0.9


def test_full_todos_dominate_merged_pr() -> None:
    """When todos are fully done, that beats the 0.9 PR signal."""
    assert combine_progress(completed=8, total=8, has_merged_pr=True) == 1.0


def test_merged_pr_with_no_todos() -> None:
    """A merged PR alone (no todos) still credits the PR progress."""
    assert combine_progress(completed=0, total=0, has_merged_pr=True) == 0.9


def test_discount_finished_phase_floors_at_residual() -> None:
    """A fully-done phase shrinks to the handoff residual, not to zero."""
    est = PERTEstimate(optimistic=2.0, most_likely=4.0, pessimistic=8.0)
    out = discounted_pert(est, progress=1.0)
    assert out.optimistic == round(2.0 * CURRENT_PHASE_RESIDUAL, 2)
    assert out.most_likely == round(4.0 * CURRENT_PHASE_RESIDUAL, 2)
    assert out.pessimistic == round(8.0 * CURRENT_PHASE_RESIDUAL, 2)


def test_discount_zero_progress_is_unchanged() -> None:
    """No progress → the estimate is untouched."""
    est = PERTEstimate(optimistic=2.0, most_likely=4.0, pessimistic=8.0)
    out = discounted_pert(est, progress=0.0)
    assert (out.optimistic, out.most_likely, out.pessimistic) == (2.0, 4.0, 8.0)


def test_discount_half_progress_halves_estimate() -> None:
    """Half done → half the remaining effort."""
    est = PERTEstimate(optimistic=2.0, most_likely=4.0, pessimistic=8.0)
    out = discounted_pert(est, progress=0.5)
    assert (out.optimistic, out.most_likely, out.pessimistic) == (1.0, 2.0, 4.0)


def test_discount_clamps_out_of_range_progress() -> None:
    """Defensive: progress > 1 floors at the residual, progress < 0 is a
    no-op — a bad caller can never inflate the estimate."""
    est = PERTEstimate(optimistic=2.0, most_likely=4.0, pessimistic=8.0)
    over = discounted_pert(est, progress=2.0)
    assert over.most_likely == round(4.0 * CURRENT_PHASE_RESIDUAL, 2)
    under = discounted_pert(est, progress=-1.0)
    assert under.most_likely == 4.0
