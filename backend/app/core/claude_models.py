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

"""Pinned Claude models — ids, tiers and list prices. The table itself.

``ai_runner.capabilities`` offers Claude's *aliases* (``sonnet``, ``opus``,
``haiku``), which the CLI resolves to whichever generation is current. That is
the right default for per-skill configuration, but some settings have to name
an exact model: the scan-synthesis default, the cross-repo merge models, and
the dropdowns that let an org pin one. Those ids were literals in six files,
which is how the settings UI came to advertise models two generations old —
and one id (``claude-sonnet-4-5-20250514``) that no longer resolves.

This module is their single source of truth, so adopting a new release is a
data edit in :data:`CLAUDE_MODELS` and nothing else. Which model a *default*
then lands on is decided in ``claude_model_defaults``, which reads this table
— import the rule from there, not from here, which would cycle.

Lives in ``core`` and is dependency-free (stdlib only) so the config, schema,
service and API layers can all import it without reaching upward.

Prices are whole US cents per million tokens — integers, so comparing two
rates is exact rather than a float equality test. Each rate is the one that
applies at *our* prompt sizes: every consumer here is a large-prompt workload,
so where a model is priced in brackets the larger bracket is recorded.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "CLAUDE_MODELS",
    "ClaudeModel",
    "ClaudeTier",
    "get_model",
    "model_ids",
    "models_in_tier",
]


class ClaudeTier(StrEnum):
    """Capability/price tier a model belongs to, cheapest first.

    Declaration order is the order the settings UI lists tiers in, so it reads
    cheapest-to-priciest without the UI sorting anything itself.
    """

    haiku = "haiku"
    sonnet = "sonnet"
    opus = "opus"
    fable = "fable"


@dataclass(frozen=True)
class ClaudeModel:
    """One pinned model: its CLI id, tier, release order and list price."""

    id: str
    label: str
    tier: ClaudeTier
    # (major, minor) — orders releases within a tier. A tuple rather than a
    # float so 5.10 would sort above 5.9, and so nothing parses the id string.
    generation: tuple[int, int]
    input_cents_per_mtok: int
    output_cents_per_mtok: int

    @property
    def price_label(self) -> str:
        """Cost hint for the dropdowns: ``$2.00 in / $10.00 out per Mtok``."""
        return (
            f"${self.input_cents_per_mtok / 100:.2f} in / "
            f"${self.output_cents_per_mtok / 100:.2f} out per Mtok"
        )

    def costs_no_more_than(self, other: "ClaudeModel") -> bool:
        """Whether this model is no pricier than ``other`` on *either* rate.

        Both axes, deliberately. A single scalar — or comparing the
        ``(input, output)`` pair, which Python orders lexicographically —
        would let a cheaper input rate outvote any output rate at all.
        """
        return (
            self.input_cents_per_mtok <= other.input_cents_per_mtok
            and self.output_cents_per_mtok <= other.output_cents_per_mtok
        )


# Anthropic's published per-million-token rates, in cents. Ordered by tier
# (cheapest first) and newest release first within a tier, which is the order
# the settings dropdowns show — append a new model to the front of its tier,
# not to the end of the tuple.
CLAUDE_MODELS: tuple[ClaudeModel, ...] = (
    # Haiku 5.5 is bracket-priced: 10/50 up to a 100K-token prompt, 50/250
    # beyond it. Recorded at the larger bracket, which is the one that applies
    # to every workload reading this table.
    ClaudeModel("claude-haiku-5-5", "Claude Haiku 5.5", ClaudeTier.haiku, (5, 5), 50, 250),
    ClaudeModel("claude-haiku-4-5", "Claude Haiku 4.5", ClaudeTier.haiku, (4, 5), 100, 500),
    ClaudeModel("claude-sonnet-5-5", "Claude Sonnet 5.5", ClaudeTier.sonnet, (5, 5), 200, 1000),
    ClaudeModel("claude-sonnet-5", "Claude Sonnet 5", ClaudeTier.sonnet, (5, 0), 200, 1000),
    ClaudeModel("claude-sonnet-4-6", "Claude Sonnet 4.6", ClaudeTier.sonnet, (4, 6), 300, 1500),
    ClaudeModel("claude-opus-5-5", "Claude Opus 5.5", ClaudeTier.opus, (5, 5), 400, 2000),
    ClaudeModel("claude-opus-5", "Claude Opus 5", ClaudeTier.opus, (5, 0), 500, 2500),
    ClaudeModel("claude-opus-4-8", "Claude Opus 4.8", ClaudeTier.opus, (4, 8), 500, 2500),
    ClaudeModel("claude-opus-4-7", "Claude Opus 4.7", ClaudeTier.opus, (4, 7), 500, 2500),
    ClaudeModel("claude-opus-4-6", "Claude Opus 4.6", ClaudeTier.opus, (4, 6), 500, 2500),
    ClaudeModel("claude-fable-5-1", "Claude Fable 5.1", ClaudeTier.fable, (5, 1), 1000, 5000),
    ClaudeModel("claude-fable-5", "Claude Fable 5", ClaudeTier.fable, (5, 0), 1000, 5000),
)

_BY_ID: dict[str, ClaudeModel] = {m.id: m for m in CLAUDE_MODELS}


def get_model(model_id: str) -> ClaudeModel | None:
    """The catalogued model with ``model_id``, or ``None``.

    ``None`` covers an alias (``"sonnet"``), another provider's id, and an id
    that has left the catalogue.
    """
    return _BY_ID.get(model_id)


def model_ids(tiers: Sequence[ClaudeTier] | None = None) -> frozenset[str]:
    """Every catalogued id, or only those in ``tiers``.

    Callers use this as an allowlist, and it is deliberately wider than what
    ``claude_model_defaults.offered_models`` lists: a model an org pinned
    before a newer release arrived stays valid, so moving a default never
    silently rewrites a deliberate choice.
    """
    wanted = set(tiers) if tiers is not None else set(ClaudeTier)
    return frozenset(m.id for m in CLAUDE_MODELS if m.tier in wanted)


def models_in_tier(tier: ClaudeTier) -> tuple[ClaudeModel, ...]:
    """Every catalogued model in ``tier``, newest release first."""
    ordered = sorted((m for m in CLAUDE_MODELS if m.tier is tier), key=lambda m: m.generation)
    return tuple(reversed(ordered))
