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

"""Tests for the complexity heuristic and LLM reconciliation (pure functions)."""

from __future__ import annotations

from app.services.estimation_heuristics import compute_complexity, reconcile_complexity


def test_thin_spec_across_many_repos_stays_low() -> None:
    """A small feature that merely touches many repos must not score as
    complex — repo spread is coordination, not scope. (The BUD-050 case:
    395-char requirements, ~9.5k tech spec, 4 repos, 0 QA → was 3.)"""
    assert compute_complexity(395, 9516, impacted_repo_count=4, qa_case_count=0) <= 2


def test_substantial_multi_repo_still_scores_high() -> None:
    """A large spec with many QA cases across several repos keeps a high
    score — the repo bump applies in full when real scope backs it."""
    assert compute_complexity(3604, 18225, impacted_repo_count=9, qa_case_count=18) == 4
    assert compute_complexity(40000, 0, impacted_repo_count=4, qa_case_count=25) == 5


def test_trivial_change_is_complexity_one() -> None:
    """A tiny single-repo tweak floors at 1."""
    assert compute_complexity(200, 200, impacted_repo_count=1, qa_case_count=0) == 1


def test_repo_count_is_monotonic_at_fixed_scope() -> None:
    """Holding content/QA fixed, more repos never lowers complexity."""
    scores = [
        compute_complexity(20000, 0, impacted_repo_count=n, qa_case_count=12)
        for n in (1, 2, 3, 4)
    ]
    assert scores == sorted(scores)


def test_scope_is_monotonic_at_fixed_repos() -> None:
    """Holding repos fixed, more content/QA never lowers complexity."""
    low = compute_complexity(200, 200, impacted_repo_count=4, qa_case_count=0)
    mid = compute_complexity(20000, 0, impacted_repo_count=4, qa_case_count=12)
    high = compute_complexity(40000, 0, impacted_repo_count=4, qa_case_count=25)
    assert low <= mid <= high


def test_reconcile_clamps_llm_within_one_of_heuristic() -> None:
    """The LLM may pull complexity down or up, but only by ±1 — neither a
    hallucinated 5 nor a lazy 1 escapes the signal-based bound."""
    assert reconcile_complexity(4, 2) == 3  # pulled down to heuristic+1
    assert reconcile_complexity(5, 2) == 3
    assert reconcile_complexity(1, 4) == 3  # pulled up to heuristic-1
    assert reconcile_complexity(2, 2) == 2  # within bound, unchanged
    assert reconcile_complexity(3, 2) == 3  # exactly +1, allowed


def test_reconcile_none_falls_back_to_heuristic() -> None:
    """No LLM rating → the heuristic stands, unchanged."""
    assert reconcile_complexity(None, 3) == 3


def test_reconcile_respects_global_bounds() -> None:
    """Clamping never produces a value outside 1..5."""
    assert reconcile_complexity(1, 1) == 1
    assert reconcile_complexity(5, 5) == 5
