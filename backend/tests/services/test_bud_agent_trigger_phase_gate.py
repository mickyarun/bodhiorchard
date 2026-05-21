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

"""Unit tests for the ``should_auto_generate_phase`` predicate.

This is the central gate that decides whether the backend fires its
own agent for a BUD phase (PM, designer, tech-planner, qa, …) or
falls through to the user's "external-LLM" path. The Figma tech-spec
flow specifically depends on the ``tech_arch`` phase staying gated off
so the Tech-Arch tab can render the copyable local-Claude prompt
instead of an unwanted server-side draft.

The predicate sits in :mod:`app.services.bud_agent_trigger`; both the
create-BUD path (:mod:`app.api.v1.bud`) and the status-transition
path read through it so they can't drift to subtly different
behaviour.
"""

import pytest

from app.services.bud_agent_trigger import should_auto_generate_phase


@pytest.mark.parametrize(
    ("phases", "phase_key", "expected"),
    [
        # External-LLM defaults: nothing on → nothing fires.
        (None, "tech_arch", False),
        ({}, "tech_arch", False),
        # Explicit False on the requested key.
        ({"tech_arch": False}, "tech_arch", False),
        # Explicit True on the requested key.
        ({"tech_arch": True}, "tech_arch", True),
        # Other phases enabled but the requested one missing — still off.
        ({"design": True}, "tech_arch", False),
        # Mixed map — only the targeted key matters.
        ({"design": True, "tech_arch": False, "testing": True}, "tech_arch", False),
        ({"design": True, "tech_arch": True}, "tech_arch", True),
        # Same predicate gates the create-BUD path's "bud" auto-spawn.
        ({"bud": True}, "bud", True),
        ({"bud": False}, "bud", False),
        # Unknown phase_key falls through to False rather than KeyError —
        # forward-compat for new phases the deployed backend doesn't know.
        ({"tech_arch": True}, "future_phase", False),
    ],
)
def test_should_auto_generate_phase_truth_table(
    phases: dict[str, bool] | None, phase_key: str, expected: bool
) -> None:
    """The predicate must be the single source of truth for the gate.

    The Figma tech-spec flow specifically depends on the
    ``{"tech_arch": False}`` (or unset) path returning False so the
    backend doesn't pre-empt the local-Claude prompt by writing an
    AI-generated tech spec the developer would then have to overwrite.
    """
    assert should_auto_generate_phase(phases, phase_key) is expected
