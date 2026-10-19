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

"""The pinned Claude catalogue and the rule that picks a tier's default.

The rule is tested through ``newest_affordable`` on *synthetic* models, not by
reading the shipped table. That matters: an earlier version of these tests
recomputed the selection the same way the implementation did, so it asserted
the code against itself and passed while the rule was wrong. Synthetic inputs
can express price shapes the catalogue does not currently contain — which is
exactly where the rule earns its keep.

Catalogue facts (ids, prices, ordering) are then asserted separately, as data
invariants, plus one list of today's expected defaults that is meant to need a
deliberate edit when a release changes an answer.
"""

import re
from pathlib import Path

import pytest

from app.core.claude_model_defaults import (
    default_for_tier,
    is_recommended,
    newest_affordable,
    offered_models,
)
from app.core.claude_models import (
    CLAUDE_MODELS,
    ClaudeModel,
    ClaudeTier,
    get_model,
    model_ids,
    models_in_tier,
)
from app.services.scan.synthesis.runner import DEFAULT_MODEL

# A complete model id, as the CLI accepts it. Date-suffixed ids are the
# specific regression this guards: the settings schema shipped a
# ``claude-sonnet-4-5-20250514`` default that had stopped resolving.
ID_PATTERN = re.compile(r"^claude-[a-z]+-\d+(-\d+)?$")

SKILLS_DIR = Path(__file__).resolve().parents[2] / "app" / "agents" / "skills"
# ``model:`` / ``iteration_model:`` in skill frontmatter, in two strengths:
# any value, to prove the format still parses, and an exact ``claude-*`` id,
# which is the only form that can go stale (an alias tracks the current
# generation by itself).
SKILL_MODEL_LINE = re.compile(r"^\s*(?:iteration_)?model:\s*\S+\s*$", re.MULTILINE)
SKILL_PINNED_ID = re.compile(r"^\s*(?:iteration_)?model:\s*(claude-\S+)\s*$", re.MULTILINE)


def model(generation: tuple[int, int], input_cents: int, output_cents: int) -> ClaudeModel:
    """A synthetic model, for exercising the rule on prices we don't ship."""
    return ClaudeModel(
        id=f"synthetic-{generation[0]}-{generation[1]}",
        label="Synthetic",
        tier=ClaudeTier.sonnet,
        generation=generation,
        input_cents_per_mtok=input_cents,
        output_cents_per_mtok=output_cents,
    )


class TestTheRule:
    """``newest_affordable``: adopt a newer release only if it costs no more."""

    def test_newer_at_the_same_price_is_adopted(self) -> None:
        """The behaviour the whole catalogue exists to deliver."""
        incumbent = model((5, 5), 200, 1000)
        newer = model((6, 0), 200, 1000)
        assert newest_affordable([incumbent, newer]) is newer

    def test_newer_and_cheaper_is_adopted(self) -> None:
        incumbent = model((5, 5), 200, 1000)
        newer = model((6, 0), 100, 500)
        assert newest_affordable([incumbent, newer]) is newer

    def test_newer_but_dearer_is_not_adopted(self) -> None:
        incumbent = model((5, 5), 200, 1000)
        newer = model((6, 0), 400, 2000)
        assert newest_affordable([incumbent, newer]) is incumbent

    def test_a_cheaper_input_rate_cannot_outvote_a_dearer_output_rate(self) -> None:
        """The defect this rule was rewritten to fix.

        Comparing ``(input, output)`` pairs with ``min()`` is lexicographic,
        so input price decides everything: a release shaving 25% off input
        while tripling output used to win. Both rates have to improve.
        """
        incumbent = model((5, 5), 200, 1000)
        newer = model((6, 0), 150, 3000)
        assert newest_affordable([incumbent, newer]) is incumbent

    def test_a_dearer_release_does_not_block_a_later_cheap_one(self) -> None:
        """The ratchet compares against the incumbent, not the previous id."""
        incumbent = model((5, 5), 200, 1000)
        skipped = model((6, 0), 500, 2500)
        later = model((7, 0), 200, 1000)
        assert newest_affordable([incumbent, skipped, later]) is later

    def test_order_of_the_input_sequence_is_irrelevant(self) -> None:
        models = [model((5, 5), 200, 1000), model((6, 0), 200, 1000), model((4, 6), 300, 1500)]
        assert newest_affordable(models) is newest_affordable(list(reversed(models)))

    def test_empty_input_is_a_programming_error(self) -> None:
        with pytest.raises(ValueError, match="at least one model"):
            newest_affordable([])


class TestCatalogueData:
    """Invariants the hand-maintained table has to keep satisfying."""

    def test_every_tier_has_a_model(self) -> None:
        for tier in ClaudeTier:
            assert models_in_tier(tier), f"no models catalogued for {tier.value}"
            assert default_for_tier(tier).tier is tier

    def test_ids_are_unique_and_undated(self) -> None:
        ids = [m.id for m in CLAUDE_MODELS]
        assert len(ids) == len(set(ids)), "duplicate model id"
        for model_id in ids:
            assert ID_PATTERN.match(model_id), f"{model_id} is not a bare model id"

    def test_tier_and_generation_pairs_are_unique(self) -> None:
        """``newest_affordable`` breaks no ties, so a clash is ambiguous."""
        pairs = [(m.tier, m.generation) for m in CLAUDE_MODELS]
        assert len(pairs) == len(set(pairs))

    def test_prices_are_positive_whole_cents(self) -> None:
        for m in CLAUDE_MODELS:
            assert isinstance(m.input_cents_per_mtok, int)
            assert isinstance(m.output_cents_per_mtok, int)
            assert m.input_cents_per_mtok > 0
            assert m.output_cents_per_mtok > 0

    def test_tiers_are_declared_and_listed_cheapest_first(self) -> None:
        """Both orderings are load-bearing: the UI does no sorting of its own.

        Appending a new model to the end of the tuple — the natural edit —
        would reorder the dropdown while every rule test still passed.
        """
        tier_order = [m.tier for m in CLAUDE_MODELS]
        assert tier_order == sorted(tier_order, key=list(ClaudeTier).index)
        for tier in ClaudeTier:
            catalogued = [m for m in CLAUDE_MODELS if m.tier is tier]
            assert catalogued == sorted(catalogued, key=lambda m: m.generation, reverse=True)
        cheapest = [default_for_tier(tier).input_cents_per_mtok for tier in ClaudeTier]
        assert cheapest == sorted(cheapest), "tier declaration order is not cheapest-first"

    def test_get_model_rejects_an_alias(self) -> None:
        """Aliases are the CLI's vocabulary, deliberately not catalogued."""
        assert get_model("sonnet") is None
        assert get_model("claude-sonnet-5-5") is not None

    def test_model_ids_filters_by_tier(self) -> None:
        sonnet_only = model_ids([ClaudeTier.sonnet])
        assert "claude-sonnet-4-6" in sonnet_only
        assert "claude-opus-5-5" not in sonnet_only
        assert sonnet_only < model_ids()


@pytest.mark.parametrize(
    ("tier", "expected"),
    [
        (ClaudeTier.haiku, "claude-haiku-5-5"),
        (ClaudeTier.sonnet, "claude-sonnet-5-5"),
        (ClaudeTier.opus, "claude-opus-5-5"),
        (ClaudeTier.fable, "claude-fable-5-1"),
    ],
)
def test_current_default_per_tier(tier: ClaudeTier, expected: str) -> None:
    """Today's answers. Update deliberately when a release changes one."""
    assert default_for_tier(tier).id == expected


class TestOfferedModels:
    """What a dropdown lists: the default, plus anything newer than it."""

    def test_offers_each_tier_default_and_nothing_superseded(self) -> None:
        offered = offered_models()
        assert all(is_recommended(m) for m in offered), "no tier has a newer release today"
        assert [m.tier for m in offered] == list(ClaudeTier)
        assert get_model("claude-sonnet-4-6") not in offered

    def test_offers_a_newer_dearer_release_the_rule_declined(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The opt-in path, which no shipped tier currently exercises.

        Both module globals are patched because ``models_in_tier`` reads the
        table in ``claude_models`` while ``offered_models`` holds its own
        reference to it.
        """
        incumbent = model((5, 5), 200, 1000)
        dearer = model((6, 0), 400, 2000)
        table = (dearer, incumbent)
        monkeypatch.setattr("app.core.claude_models.CLAUDE_MODELS", table)
        monkeypatch.setattr("app.core.claude_model_defaults.CLAUDE_MODELS", table)

        assert default_for_tier(ClaudeTier.sonnet) is incumbent
        offered = offered_models([ClaudeTier.sonnet])
        assert set(offered) == {incumbent, dearer}
        assert not is_recommended(dearer)

    def test_restricts_to_the_requested_tiers(self) -> None:
        offered = offered_models([ClaudeTier.sonnet, ClaudeTier.opus])
        assert {m.tier for m in offered} == {ClaudeTier.sonnet, ClaudeTier.opus}


class TestLivePinnedIds:
    """Every exact model id the running system names must be catalogued."""

    def test_synthesis_default(self) -> None:
        resolved = get_model(DEFAULT_MODEL)
        assert resolved is not None, f"{DEFAULT_MODEL} is not catalogued"
        assert is_recommended(resolved)

    def test_skill_frontmatter(self) -> None:
        """Closes the rot that started this: a pinned id nothing validates.

        ``designer.md`` pins ``iteration_model`` to an exact Haiku release.
        Nothing resolves it against the catalogue at runtime, so it would go
        stale silently, exactly as the six literals did.

        Finding no pinned ids is a pass, not a failure: switching the last one
        to an alias is the better end state, since an alias tracks the current
        generation on its own. The format itself is checked separately, so
        this cannot quietly stop looking.
        """
        bodies = {path.name: path.read_text() for path in sorted(SKILLS_DIR.glob("*.md"))}
        assert bodies, f"no skill files under {SKILLS_DIR}"
        assert any(SKILL_MODEL_LINE.search(body) for body in bodies.values()), (
            "no model: line parsed — has the frontmatter format changed?"
        )
        stale = {
            (name, model_id)
            for name, body in bodies.items()
            for model_id in SKILL_PINNED_ID.findall(body)
            if get_model(model_id) is None
        }
        assert not stale, f"skill frontmatter names uncatalogued models: {sorted(stale)}"
