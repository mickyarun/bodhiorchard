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

"""Prompt builder for the post-close Learning Agent.

The recap is grounded entirely on data the prompt builder pre-fetches
and inlines as JSON inside the prompt body — there is no MCP read tool
for these metrics. Rationale: the agent reads, never writes, and the
data is in scope at prompt-build time. An MCP tool would only add
round-trip latency and an extra serialization contract to maintain.

Cross-BUD context: the builder pulls the top-N (default 3) most
semantically similar prior retrospectives via cosine over
``feature_learnings.embedding`` and injects them as few-shot examples
so the recap can call out trends (e.g. "the design phase has dragged
on the last 3 similar BUDs").
"""

import json
import uuid
from typing import Any

import structlog

from app.models.bud import BUDDocument
from app.repositories.feature_learning import FeatureLearningRepository
from app.services.embedding_service import embedding_service
from app.services.skill_loader import Skill

logger = structlog.get_logger(__name__)

PRIOR_RECAP_LIMIT = 3
PRIOR_RECAP_SNIPPET_CHARS = 1_500


def _summarize_bud_for_embedding(bud: BUDDocument) -> str:
    """Concatenate the BUD's identity + brief into a single embedding input."""
    parts = [
        bud.title or "",
        (bud.requirements_md or "")[:1_500],
    ]
    return "\n\n".join(p for p in parts if p)


async def _fetch_prior_recaps(
    db: Any,
    org_id: uuid.UUID,
    bud: BUDDocument,
) -> list[dict[str, str]]:
    """Top-3 prior retrospectives most semantically similar to this BUD.

    Embeds the current BUD's title + requirements (NOT the new metrics
    JSON) so the similarity hits are about the work itself, not about
    the numerical shape. Returns an empty list when the BUD's content
    can't be embedded — the prompt builder is resilient to this.
    """
    try:
        embedding = await embedding_service.embed(_summarize_bud_for_embedding(bud))
    except Exception:
        logger.warning("learning_prompt_embed_failed", bud_id=str(bud.id))
        return []

    repo = FeatureLearningRepository(db, org_id=org_id)
    similar = await repo.find_similar(
        embedding,
        limit=PRIOR_RECAP_LIMIT,
        exclude_bud_id=bud.id,
    )
    out: list[dict[str, str]] = []
    for row in similar:
        if not row.retrospective_md:
            continue
        out.append(
            {
                "bud_id": str(row.bud_id),
                "retrospective_md": row.retrospective_md[:PRIOR_RECAP_SNIPPET_CHARS],
            }
        )
    return out


def _format_prompt_body(
    skill: Skill,
    bud: BUDDocument,
    metrics: dict[str, Any],
    prior_recaps: list[dict[str, str]],
) -> str:
    """Assemble the skill body, BUD identity, structured metrics, and prior recaps."""
    prior_block = (
        json.dumps(prior_recaps, indent=2)
        if prior_recaps
        else "(no prior retrospectives available — write the first one for this complexity bucket)"
    )
    return (
        f"{skill.prompt}\n\n"
        f"## BUD\n"
        f"Number: BUD-{bud.bud_number:03d}\n"
        f"Title: {bud.title}\n\n"
        f"## Original PRD (excerpt)\n"
        f"{(bud.requirements_md or '')[:2_000]}\n\n"
        f"## Structured metrics for this BUD\n"
        f"```json\n{json.dumps(metrics, indent=2, default=str)}\n```\n\n"
        f"## Prior retrospectives from similar BUDs (most-similar first)\n"
        f"{prior_block}\n\n"
        f"## Task\n"
        f"Write the retrospective markdown for this BUD. The output is read by\n"
        f"the team on the BUD detail Learnings tab and used as cross-BUD\n"
        f"context for future recaps. Follow the skill's workflow exactly.\n"
    )


async def build_learning_prompt(
    bud: BUDDocument,
    skill: Skill,
    org_id: uuid.UUID,
    db: Any,
) -> tuple[str, str | None]:
    """Build the prompt for the post-close Learning Agent.

    Pulls the freshly-persisted ``FeatureLearning.metrics`` envelope
    from the DB (written seconds earlier by
    ``bud_metrics.compute_and_persist``) and injects it inline, then
    appends up to three vector-similar prior recaps for trend grounding.
    Returns ``(prompt, working_dir=None)`` — the agent doesn't run
    against a repo working directory.
    """
    repo = FeatureLearningRepository(db, org_id=org_id)
    learning = await repo.get_for_bud(bud.id)
    if learning is None or not learning.metrics:
        logger.warning(
            "learning_prompt_no_metrics_envelope",
            bud_id=str(bud.id),
            bud_number=bud.bud_number,
        )
        # Defensive: build a usable prompt anyway so the agent doesn't
        # silently degrade into "(no data)" output — a missing envelope
        # is a bug we want surfaced as a written recap that flags it.
        metrics: dict[str, Any] = {"_warning": "metrics envelope missing"}
    else:
        metrics = dict(learning.metrics)

    prior_recaps = await _fetch_prior_recaps(db, org_id, bud)
    prompt = _format_prompt_body(skill, bud, metrics, prior_recaps)
    return prompt, None
