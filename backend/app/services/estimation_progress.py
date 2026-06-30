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

"""Progress-aware discount for the BUD's current phase.

The estimator budgets each remaining phase by lifecycle *status*: a BUD in
``development`` gets the whole development phase re-estimated from scratch,
even when its todos are all done and a PR has merged — it just hasn't been
transitioned yet. That over-states the timeline (a code-complete BUD still
shows weeks of "development" ahead).

This reads how much of the current phase is actually finished — completed
todos for that phase, plus a merged PR as a strong signal for code-producing
phases — and scales only that phase's effort by what remains. Downstream
phases are untouched: they have not started, so their estimates stand.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.repositories.bud_todo import BUDTodoRepository
from app.repositories.pull_request import PullRequestRepository
from app.services.estimation_engine import PERTEstimate

logger = structlog.get_logger(__name__)

# Phases whose work is delivered via PRs — a merged PR there is a strong
# "the code work is done" signal, independent of whether todos were ticked.
_PR_BACKED_PHASES = {"development", "code_review"}
# Progress credited to a PR-backed phase that already has a merged PR.
_MERGED_PR_PROGRESS = 0.9
# Floor on the discounted phase: even a fully-done phase keeps a little
# wall-clock for handoff to the next stage, so it never collapses to zero.
CURRENT_PHASE_RESIDUAL = 0.1


def combine_progress(completed: int, total: int, has_merged_pr: bool) -> float:
    """Pure: stronger of the completed-todo ratio and the merged-PR signal.

    A BUD can have its PR merged before every todo is ticked, and vice
    versa, so we take the max. No todos and no merged PR → 0.0 (no discount).
    Split from the IO below so it is unit-testable without a session.
    """
    todo_ratio = completed / total if total > 0 else 0.0
    pr_ratio = _MERGED_PR_PROGRESS if has_merged_pr else 0.0
    return max(todo_ratio, pr_ratio)


async def current_phase_progress(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
) -> float:
    """Fraction of the BUD's current phase already completed, in [0, 1].

    Combines the completed-todo ratio for the current phase with a merged-PR
    signal (only for PR-backed phases) via :func:`combine_progress`.

    The todo query keys on the BUD's *current* phase string. AI-generated
    todos are all tagged ``development`` (``todo_parser``), while Jira-imported
    todos carry their source phase (``todo_sync``), so keying on the live
    status is the forward-compatible choice — and it is intentionally how the
    signal stays scoped. Phases with no todos in their domain (e.g. ``testing``,
    ``uat``) legitimately return 0.0: we simply have no completion data for
    them, so the phase is budgeted in full rather than guessed at. ``code_review``
    still gets its signal from the merged-PR path below.
    """
    phase = bud.status.value if isinstance(bud.status, BUDStatus) else bud.status

    completed, total = await BUDTodoRepository(db, org_id=org_id).phase_completion(bud.id, phase)

    has_merged_pr = phase in _PR_BACKED_PHASES and await PullRequestRepository(
        db, org_id=org_id
    ).has_merged_for_bud(bud.id)

    return combine_progress(completed, total, has_merged_pr)


def discounted_pert(est: PERTEstimate, progress: float) -> PERTEstimate:
    """Scale a phase's PERT triple by the work that remains (1 − progress).

    Floored at ``CURRENT_PHASE_RESIDUAL`` so a finished phase still carries a
    small handoff cost rather than vanishing. ``progress`` is clamped to
    [0, 1] for safety, but a value outside that range is a contract violation
    (``combine_progress`` only emits [0, 1]) — most likely a ``completed >
    total`` accounting bug upstream — so we warn rather than absorb it silently.
    """
    if not 0.0 <= progress <= 1.0:
        logger.warning(
            "discounted_pert_progress_out_of_range",
            progress=progress,
            action="clamped to [0,1]; indicates a completed>total accounting bug upstream",
        )
    remaining = max(CURRENT_PHASE_RESIDUAL, 1.0 - max(0.0, min(1.0, progress)))
    return PERTEstimate(
        optimistic=round(est.optimistic * remaining, 2),
        most_likely=round(est.most_likely * remaining, 2),
        pessimistic=round(est.pessimistic * remaining, 2),
    )
