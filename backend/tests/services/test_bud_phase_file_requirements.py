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

"""Which BUD phases actually need a filesystem, and which only look like it.

Each phase was handed a ``working_dir`` and so was refused wholesale on a
provider without file access. That was right for some phases and wrong for
others, and the difference is not obvious from the call site — it lives in what
the prompt tells the agent to do:

* ``tech_arch`` explores through the code-intel MCP tools (the cached call graph
  in Postgres) and its own skill forbids bash search. Its working_dir was just
  ``repo_triples[0]`` — an arbitrary repo — so refusing it bought nothing.
* ``code_review`` / ``testing`` are handed ``git fetch`` / ``git diff`` commands
  to run. A diff has no call-graph equivalent, so refusing them is the honest
  outcome; dropping their path would buy a confident review of unseen code.

These tests pin that split so a future edit can't quietly flip a phase into
generating a spec about code it never read.
"""

from app.services.bud_agent_handler import _GRAPH_NAVIGABLE_PHASES
from app.services.skill_loader import load_skill

# The graph tools tech-planner's own instructions mandate ("Use bodhi code-intel
# MCP tools ... Do NOT use bash find / grep / ls").
_CODE_INTEL_TOOLS = {"code_query", "code_context", "code_impact"}


def test_tech_arch_navigates_by_graph_not_filesystem() -> None:
    assert "tech_arch" in _GRAPH_NAVIGABLE_PHASES


def test_review_and_testing_are_not_graph_navigable() -> None:
    """Their prompts issue git commands; a diff has no graph equivalent."""
    assert "code_review" not in _GRAPH_NAVIGABLE_PHASES
    assert "testing" not in _GRAPH_NAVIGABLE_PHASES


def test_tech_planner_declares_the_tools_its_own_prompt_mandates() -> None:
    """The skill body orders the agent to use the code-intel tools and forbids
    bash search — but ``mcp_tools`` did not expose them, so the instruction was
    unfollowable on every provider, and the file-less path had nothing at all to
    navigate with. Routing tech_arch around the filesystem depends on these.
    """
    declared = set(load_skill("tech-planner").mcp_tools)

    assert declared >= _CODE_INTEL_TOOLS, f"missing: {_CODE_INTEL_TOOLS - declared}"


def test_graph_navigable_phases_declare_their_graph_tools() -> None:
    """Any phase routed around the filesystem must be able to reach the graph,
    or it would plan against nothing but the prompt."""
    slug_for_phase = {"tech_arch": "tech-planner"}
    for phase in _GRAPH_NAVIGABLE_PHASES:
        declared = set(load_skill(slug_for_phase[phase]).mcp_tools)
        assert declared >= _CODE_INTEL_TOOLS, f"{phase} cannot reach the call graph"
