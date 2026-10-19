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

"""Which model the cross-repo merge settings resolve to, and which they offer.

Two halves of one contract, tested together because the bug they guard against
is a disagreement between them: the dropdown offering a model that
``get_merge_models`` would discard on read, which is how an org ends up with a
setting that appears saved and does nothing.
"""

import pytest

from app.api.v1.ai_settings import serialize_merge_models
from app.config import settings
from app.core.claude_model_defaults import default_for_tier
from app.core.claude_models import ClaudeTier
from app.services.org_settings import MERGE_MODEL_TIERS, get_merge_models


@pytest.fixture
def platform_defaults() -> tuple[str, str]:
    """What an org with no override of its own should land on."""
    return default_for_tier(ClaudeTier.sonnet).id, default_for_tier(ClaudeTier.opus).id


class TestResolution:
    """``get_merge_models``: org override → env default → the price rule."""

    def test_unconfigured_org_gets_the_current_tier_defaults(
        self, platform_defaults: tuple[str, str]
    ) -> None:
        assert get_merge_models(None) == platform_defaults
        assert get_merge_models({}) == platform_defaults
        assert get_merge_models({"llm": {}}) == platform_defaults

    def test_org_override_is_honoured_even_once_superseded(
        self, platform_defaults: tuple[str, str]
    ) -> None:
        """A pin made before a newer release must not be silently rewritten."""
        chosen = get_merge_models({"llm": {"merge_model_default": "claude-sonnet-4-6"}})
        assert chosen == ("claude-sonnet-4-6", platform_defaults[1])

    def test_an_env_default_outranks_the_price_rule(
        self, monkeypatch: pytest.MonkeyPatch, platform_defaults: tuple[str, str]
    ) -> None:
        """``LLMConfig`` is the operator's lever; empty means "ask the rule"."""
        monkeypatch.setattr(settings.llm, "merge_model_default", "claude-sonnet-5")
        assert get_merge_models(None) == ("claude-sonnet-5", platform_defaults[1])

    @pytest.mark.parametrize("configured", ["claude-haiku-4-5", "sonnet", "not-a-model-at-all"])
    def test_an_env_default_outside_the_merge_tiers_falls_back(
        self,
        monkeypatch: pytest.MonkeyPatch,
        configured: str,
        platform_defaults: tuple[str, str],
    ) -> None:
        """The operator's lever gets the same check as the org's pin.

        It did not: the env value was the fallback, so it skipped the
        allowlist entirely and ``LLM_MERGE_MODEL_DEFAULT=not-a-model-at-all``
        reached ``ClaudeRunnerConfig`` verbatim. Haiku is the pointed case —
        a real model, but 200K context against a prompt sized for 1M.
        """
        monkeypatch.setattr(settings.llm, "merge_model_default", configured)
        assert get_merge_models(None) == platform_defaults

    @pytest.mark.parametrize(
        "pinned",
        [
            "claude-sonnet-9-9",  # does not exist
            "sonnet",  # an alias, not an exact id
            "claude-haiku-5-5",  # real, but below the tiers merge accepts
            "claude-fable-5-1",  # real, but 5x Opus
            "",
        ],
    )
    def test_a_model_outside_the_merge_tiers_falls_back(
        self, pinned: str, platform_defaults: tuple[str, str]
    ) -> None:
        """Falling back beats running an unknown or ill-fitting model.

        Haiku is the pointed case: it is a perfectly real model, but the merge
        prompt is sized for a 1M-token context and Haiku 4.5 is the one 200K
        model catalogued — so a pin on that tier truncates rather than
        degrades, and the escalation setting pointing *down* a tier defeats
        its own purpose.
        """
        assert get_merge_models({"llm": {"merge_model_default": pinned}}) == platform_defaults


class TestOfferedChoices:
    """``serialize_merge_models``: what the two dropdowns are allowed to show."""

    def test_every_served_model_would_be_accepted_on_read(
        self, platform_defaults: tuple[str, str]
    ) -> None:
        """The contract: the UI cannot offer what the backend would discard."""
        for served in serialize_merge_models():
            if not served["offered"]:
                continue
            chosen, _ = get_merge_models({"llm": {"merge_model_default": served["id"]}})
            assert chosen == served["id"], f"{served['id']} is offered but not accepted"

    def test_only_merge_tiers_are_served(self) -> None:
        tiers = {served["tier"] for served in serialize_merge_models()}
        assert tiers == {tier.value for tier in MERGE_MODEL_TIERS}

    def test_the_recommended_model_is_each_tier_default(self) -> None:
        recommended = {s["id"] for s in serialize_merge_models() if s["recommended"]}
        assert recommended == {default_for_tier(tier).id for tier in MERGE_MODEL_TIERS}

    def test_superseded_models_are_served_but_not_offered(self) -> None:
        """They need a label so an existing pin renders as its name."""
        by_id = {served["id"]: served for served in serialize_merge_models()}
        stale = by_id["claude-sonnet-4-6"]
        assert stale["offered"] is False
        assert stale["recommended"] is False
        assert stale["label"] == "Claude Sonnet 4.6"
        assert stale["price_label"] == "$3.00 in / $15.00 out per Mtok"
