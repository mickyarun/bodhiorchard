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

"""Which pinned model a default lands on, and which ones a dropdown offers.

Split from ``claude_models`` so that module holds only the table: this one
reads it, so importing back the other way would cycle. Call sites import the
rule from here and the table from there.

:func:`newest_affordable` is the standing rule, written once. Everything else
in this module is that rule applied — to a tier, to a single model, or to the
list a settings dropdown shows.
"""

from collections.abc import Sequence

from app.core.claude_models import CLAUDE_MODELS, ClaudeModel, ClaudeTier, models_in_tier

__all__ = [
    "default_for_tier",
    "is_recommended",
    "newest_affordable",
    "offered_models",
]


def newest_affordable(models: Sequence[ClaudeModel]) -> ClaudeModel:
    """Walk releases oldest to newest, adopting each that costs no more.

    A ratchet, and the standing rule for moving a default: a newer release
    replaces the incumbent only when it is no pricier on *both* rates, so an
    unchanged or lower price is adopted automatically while a price rise never
    is. A release that trades a cheaper input rate for a dearer output one is
    not an adoption — it is a price change, and has to be chosen deliberately
    (:func:`offered_models` is where it stays available).

    Args:
        models: Models to choose between — normally one tier's releases.
            Order does not matter; ``generation`` decides it.

    Returns:
        The adopted model.

    Raises:
        ValueError: If ``models`` is empty.
    """
    ordered = sorted(models, key=lambda m: m.generation)
    if not ordered:
        raise ValueError("newest_affordable needs at least one model")
    chosen = ordered[0]
    for candidate in ordered[1:]:
        if candidate.costs_no_more_than(chosen):
            chosen = candidate
    return chosen


def default_for_tier(tier: ClaudeTier) -> ClaudeModel:
    """The model to default to in ``tier`` — see :func:`newest_affordable`."""
    siblings = models_in_tier(tier)
    if not siblings:
        raise ValueError(f"no Claude model catalogued for tier {tier.value!r}")
    return newest_affordable(siblings)


def is_recommended(model: ClaudeModel) -> bool:
    """Whether ``model`` is its tier's default.

    Named for what it checks. The rest of a tier splits two ways, and the
    distinction matters to the UI: an *older* release is superseded and worth
    hiding, while one *newer* than the default was skipped only for raising a
    price — it is the latest model, and :func:`offered_models` keeps it.
    """
    return default_for_tier(model.tier).id == model.id


def offered_models(tiers: Sequence[ClaudeTier] | None = None) -> tuple[ClaudeModel, ...]:
    """Each tier's default, plus any release newer than it.

    What a dropdown should list, in catalogue order. The newer entries are the
    deliberate opt-ins the rule declines to adopt on its own; offering them is
    the only way to pick a brand-new release that costs more, and leaving them
    out would make "stays opt-in" untrue.

    Superseded older releases are left out: whatever replaced each of them is
    no pricier, so there is no reason to pick one. A stored pin on one still
    resolves — see ``claude_models.model_ids``.

    Args:
        tiers: Restrict to these tiers. ``None`` means every tier.
    """
    wanted = set(tiers) if tiers is not None else set(ClaudeTier)
    defaults = {tier: default_for_tier(tier) for tier in wanted}
    return tuple(
        model
        for model in CLAUDE_MODELS
        if model.tier in wanted and model.generation >= defaults[model.tier].generation
    )
