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

"""The tech-planner skill's Mermaid rule never asks for quotes inside labels.

The skill once told the model to "use straight quotes", and it wrote
``K[Show "n of 3" count]``, which Mermaid can't parse. The rule now says a
double quote may only wrap a whole label, with inner quotes as ``#quot;``.
"""

from __future__ import annotations

import re

from app.services.skill_loader import load_skill


def _mermaid_rules() -> str:
    prompt = load_skill("tech-planner").prompt
    start = prompt.index("No double quotes inside a label")
    return prompt[start : prompt.index("\n", start)]


def test_rule_forbids_inner_quotes_and_names_the_escape() -> None:
    """The rule shows both safe forms: reworded, or whole-label quoted with #quot;."""
    rule = _mermaid_rules()
    assert "K[Show n of 3 count]" in rule
    assert 'K["Show #quot;n of 3#quot; count"]' in rule


def test_skill_no_longer_recommends_straight_quotes() -> None:
    """The old instruction that produced the broken labels is gone."""
    prompt = load_skill("tech-planner").prompt
    assert re.search(r"straight quotes?\s*`\"`", prompt) is None


def test_every_example_in_the_rule_quotes_whole_labels_only() -> None:
    """Each recommended label either has no quote or is wrapped end to end."""
    examples = re.findall(r"\(`([^`]+)`, `([^`]+)`\)", _mermaid_rules())
    assert examples, "rule should carry worked examples"
    for node, edge in examples:
        for label in (node[node.index("[") + 1 : -1], edge.split("|")[1]):
            inner = label[1:-1] if label.startswith('"') and label.endswith('"') else label
            assert '"' not in inner, label
