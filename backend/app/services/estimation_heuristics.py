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

"""LLM-fallback heuristics: a deterministic scoring + spread used when
the AI-PERT call fails or is unavailable.

These are deliberately pessimistic — the goal is to keep the panel
showing _some_ forecast rather than crash, not to be a primary signal.
Lives apart from ``estimation_engine`` so the engine module can stay
focused on the Monte Carlo / PERT math used in the happy path.
"""

from __future__ import annotations

from app.services.estimation_engine import DEFAULT_PHASE_DAYS, PERTEstimate

# Pessimism thresholds for ``compute_complexity``. Content volume is a
# weak signal because AI agents write verbose specs even for simple
# features, so the cut-offs are intentionally high. Multi-repo and QA
# coverage are stronger signals — those scale aggressively.
_CONTENT_LEN_HIGH = 30_000
_CONTENT_LEN_MEDIUM = 15_000
_QA_HIGH = 20
_QA_MEDIUM = 10
_QA_LOW = 5

# Repo count is a *coordination* signal, not a scope signal on its own: a
# 4-repo change with a one-paragraph spec and no QA is small work spread
# thin, not a complex feature. The raw bump below is scaled by how much
# real scope the content + QA signals show (``_REPO_SCOPE_*``), with a
# floor so genuine multi-repo coordination still counts for something.
_REPO_BUMP_HIGH = 2.0  # >= 4 repos
_REPO_BUMP_MEDIUM = 1.5  # 3 repos
_REPO_BUMP_LOW = 0.5  # 2 repos
_REPO_SCOPE_FLOOR = 0.25  # min fraction of the repo bump always credited
_REPO_SCOPE_FULL_AT = 1.0  # content+QA evidence at which the full bump applies

# The LLM rates complexity independently from the feature's actual
# substance (which the length/repo heuristic can't see); we keep its
# rating only within ±this of the heuristic, as a sanity bound.
_COMPLEXITY_CLAMP = 1

# ``default_pert_spread`` scaling factors. ``complexity / 3`` keeps a
# complexity-3 BUD at the per-phase baseline; queue and workload each
# stretch the estimate proportionally to load.
_COMPLEXITY_DIVISOR = 3.0
_QUEUE_FACTOR_PER_BUD = 0.3
_WORKLOAD_FACTOR_PER_BUD = 0.2

# PERT spread coefficients for the fallback path. 0.6× / 1.0× / 2.0×
# of the scaled base = O / M / P — wide enough that the resulting
# Monte Carlo doesn't underestimate when we're already in
# fallback-because-LLM-failed territory.
_FALLBACK_OPTIMISTIC_RATIO = 0.6
_FALLBACK_PESSIMISTIC_RATIO = 2.0


def compute_complexity(
    requirements_len: int,
    tech_spec_len: int,
    impacted_repo_count: int,
    qa_case_count: int,
) -> int:
    """Derive a 1–5 complexity score from BUD signals.

    Weights repo count and QA cases heavily (actual scope indicators);
    content length is a weak signal because AI-generated specs are
    verbose even for trivial work.
    """
    content_bump = 0.0
    content_len = requirements_len + tech_spec_len
    if content_len > _CONTENT_LEN_HIGH:
        content_bump = 1.0
    elif content_len > _CONTENT_LEN_MEDIUM:
        content_bump = 0.5

    qa_bump = 0.0
    if qa_case_count > _QA_HIGH:
        qa_bump = 1.5
    elif qa_case_count > _QA_MEDIUM:
        qa_bump = 1.0
    elif qa_case_count > _QA_LOW:
        qa_bump = 0.5

    repo_raw = 0.0
    if impacted_repo_count >= 4:
        repo_raw = _REPO_BUMP_HIGH
    elif impacted_repo_count >= 3:
        repo_raw = _REPO_BUMP_MEDIUM
    elif impacted_repo_count >= 2:
        repo_raw = _REPO_BUMP_LOW

    # Scale the repo bump by content+QA scope evidence: a thin-spec change
    # across many repos stays small; a substantial multi-repo change still
    # scores high. The floor keeps multi-repo coordination from counting
    # as exactly zero.
    scope_signal = content_bump + qa_bump
    repo_scale = _REPO_SCOPE_FLOOR + (1.0 - _REPO_SCOPE_FLOOR) * min(
        1.0, scope_signal / _REPO_SCOPE_FULL_AT
    )

    score = 1.0 + content_bump + qa_bump + repo_raw * repo_scale
    return max(1, min(5, round(score)))


def reconcile_complexity(llm_complexity: int | None, heuristic_complexity: int) -> int:
    """Blend the LLM's independent complexity rating with the heuristic.

    The LLM sees the feature's actual substance the length/repo heuristic
    cannot (a 4-repo change that is really a one-line version bump, or a
    short spec hiding deep work). We trust its rating, but only within
    ``±_COMPLEXITY_CLAMP`` of the heuristic, so neither a hallucinated 5 nor
    a lazy 1 escapes the signal-based bound. ``None`` (LLM gave no rating)
    falls back to the heuristic unchanged.
    """
    if llm_complexity is None:
        return heuristic_complexity
    low = max(1, heuristic_complexity - _COMPLEXITY_CLAMP)
    high = min(5, heuristic_complexity + _COMPLEXITY_CLAMP)
    return max(low, min(high, llm_complexity))


def default_pert_spread(
    complexity: int,
    backlog_depth: int,
    assignee_workload: int,
    phase_order: list[str] | None = None,
) -> dict[str, PERTEstimate]:
    """Generate conservative PERT spreads when the LLM is unavailable.

    Scales base durations by complexity (1–5), backlog depth, and
    workload. Pessimistic by design — the fallback path should err on
    the side of over-promising slack rather than missing dates.
    """
    complexity_factor = complexity / _COMPLEXITY_DIVISOR
    queue_factor = 1 + (backlog_depth * _QUEUE_FACTOR_PER_BUD)
    workload_factor = 1 + (assignee_workload * _WORKLOAD_FACTOR_PER_BUD)
    combined = queue_factor * workload_factor

    phases_to_iterate = phase_order if phase_order is not None else list(DEFAULT_PHASE_DAYS.keys())

    result: dict[str, PERTEstimate] = {}
    for phase in phases_to_iterate:
        base = DEFAULT_PHASE_DAYS.get(phase)
        if base is None:
            continue
        scaled = base * complexity_factor * combined
        result[phase] = PERTEstimate(
            optimistic=round(scaled * _FALLBACK_OPTIMISTIC_RATIO, 1),
            most_likely=round(scaled, 1),
            pessimistic=round(scaled * _FALLBACK_PESSIMISTIC_RATIO, 1),
        )
    return result
