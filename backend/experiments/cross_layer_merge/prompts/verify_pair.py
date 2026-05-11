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

"""Verifier prompt builder for the cross-layer merge sandbox.

This module is the **iteration target** — tweak ``DECISION_RULES`` and
``RESPONSE_FORMAT`` while watching the merge results converge on
seed data. When promoting to production, copy this file to
``backend/app/scan/cross_layer/prompts.py`` (the production version
will swap ``query_xlm_features`` references for ``query_repo_features``).
"""

from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Tunable copy. Edit the two strings below to iterate on merge strictness.
# ---------------------------------------------------------------------------

DECISION_RULES = """
DECISION RULES

The purpose of merging is **impact analysis**: when a developer is
about to make a change, knowing which repos will be touched. So the
test is not "are these features the same?" but "would a typical
change to one require coordinated changes to the other?"

1. IMPACT-COUPLED → MERGE. Two features are impact-coupled when a
   typical change to one would likely require coordinated changes to
   the other. Strong signals:
   - One sends a message / payload / event that the other receives or
     consumes (e.g. backend FCM sender + frontend service worker
     receiver — changing payload format breaks both).
   - One exposes an HTTP endpoint that the other calls (UI form +
     backend handler — changing request schema breaks both).
   - One writes to a queue/topic that the other reads.
   - They share a contract: schema, event format, routing key, error
     code set, retry semantics.
   - They implement the **same product capability across layers**
     (e.g. "OTP request UI" + "OTP generation/validation backend" →
     same product feature: consumer authentication).

2. SHARED INFRASTRUCTURE WITHOUT PRODUCT COUPLING → DO NOT merge.
   Generic utilities that happen to be referenced by both but where
   neither implements a specific feature behaviour (logging, error
   handling, base classes, generic helpers).

3. DIFFERENT PRODUCT FEATURES → DO NOT merge. No shared product
   capability and no payload/contract coupling.

Important reframings:

- "Independently useful" or "could be replaced separately" is NOT a
  reason to keep features apart. A frontend button and the backend
  endpoint it POSTs to are also "independently replaceable" with
  stubs — but they are still impact-coupled. The right test is
  whether a typical change requires coordinated work, not whether
  they could in principle be swapped.

- "Send" and "receive" of the same message are NOT separate
  features. They share a payload contract — changing the payload
  schema breaks both. That's the textbook impact-coupling case.
  MERGE them.

- Cross-layer pairs (frontend ↔ backend ↔ processor) implementing
  the same product feature are the highest-value merge targets. The
  whole point is to surface "this BUD touches both layers" without
  the developer guessing.

When in doubt, prefer to MERGE. For impact analysis, a missed merge
silently hides risk (the developer doesn't know to update the other
repo). A wrong merge is visible and easy to split later. The cost
asymmetry favours merging.

Signals (strongest → weakest):
- Explicit contract overlap (HTTP route hits endpoint, FCM sender ↔
  receiver of same topic, queue producer ↔ consumer) → STRONGEST.
- Tags overlap (both "auth", both "payments", both "notifications")
  → strong.
- Title overlap with shared product noun ("OTP", "Magic Link",
  "Push Notifications") → strong, especially across layers.
- Description string overlap → moderate (vocabulary often differs
  across layers but real same-capability pairs share noun phrases).
"""

RESPONSE_FORMAT = """
RESPOND WITH ONLY A SINGLE JSON OBJECT, NO PROSE BEFORE OR AFTER.

If you find a SAME-CAPABILITY match:
{"action": "merge", "canonical_synth_id": "<source-id>",
 "absorb_synth_ids": ["<candidate-id-1>", ...],
 "rationale": "<one sentence>"}

If no candidate is SAME-CAPABILITY:
{"action": "no_match", "rationale": "<one sentence>"}

The "canonical_synth_id" should always be the SOURCE feature's id.
"""


# ---------------------------------------------------------------------------
# Prompt assembly. Stable; do not edit unless changing the field set.
# ---------------------------------------------------------------------------


@dataclass
class FeatureView:
    """Minimal projection of an XLMSynthesizedFeature for prompting."""

    synth_id: str
    title: str
    description: str
    capabilities: dict[str, Any]
    tags: list[str]
    cluster_names: list[str]
    code_paths: list[str]
    similarity: float | None = None


@dataclass
class RepoView:
    """Minimal projection of an XLMTrackedRepo for prompting."""

    name: str
    layer: str
    tech_stack: str | None


def _format_feature(label: str, repo: RepoView, feat: FeatureView, indent: str = "  ") -> str:
    sim_tag = (
        f" (prefilter cosine similarity: {feat.similarity:.3f})"
        if feat.similarity is not None
        else ""
    )
    code_paths = (
        "\n".join(f"{indent}{indent}- {p}" for p in feat.code_paths[:5])
        or f"{indent}{indent}(none)"
    )
    return (
        f"{label}: {feat.synth_id}{sim_tag}\n"
        f"{indent}Repo:        {repo.name} ({repo.layer}, {repo.tech_stack or '?'})\n"
        f"{indent}Title:       {feat.title}\n"
        f"{indent}Description: {feat.description}\n"
        f"{indent}Capabilities: {feat.capabilities}\n"
        f"{indent}Tags:        {feat.tags}\n"
        f"{indent}Clusters:    {feat.cluster_names}\n"
        f"{indent}Code paths:\n{code_paths}\n"
    )


def build_prompt(
    *,
    source_repo: RepoView,
    source_feature: FeatureView,
    target_repo: RepoView,
    candidates: list[FeatureView],
) -> str:
    """Compose the full prompt sent to Claude for one source feature."""
    if not candidates:
        raise ValueError("build_prompt requires at least one candidate")

    intro = (
        "You are deciding whether two features describe the SAME end-user "
        "capability implemented in different layers/services of the same product. "
        "You are comparing one SOURCE feature against a small set of CANDIDATE "
        "features from a paired repository."
    )

    source_block = _format_feature("SOURCE FEATURE", source_repo, source_feature)
    candidate_blocks = [
        _format_feature(f"CANDIDATE {i + 1}", target_repo, cand)
        for i, cand in enumerate(candidates)
    ]

    return "\n\n".join(
        [
            intro,
            source_block,
            "CANDIDATES:\n" + "\n".join(candidate_blocks),
            DECISION_RULES.strip(),
            RESPONSE_FORMAT.strip(),
        ]
    )


# ---------------------------------------------------------------------------
# Cluster-merge prompt — used by ``merge.runner`` when a cosine cluster has
# 2+ members. Claude sees the canonical (first member) plus N candidate
# siblings drawn from possibly N different repos / layers, plus optionally
# a small set of pre-existing canonicals to attach to.
# ---------------------------------------------------------------------------


def build_cluster_prompt(
    *,
    canonical_repo: RepoView,
    canonical_feature: FeatureView,
    candidates: list[tuple[RepoView, FeatureView]],
    related_existing: list[tuple[str, str]] | None = None,
) -> str:
    """Compose the full prompt for a multi-member cluster decision.

    ``candidates`` carries (repo, feature) tuples because cluster members
    may come from any combination of layers — we surface each member's
    repo + layer inline so Claude can apply the cross-layer reasoning
    rules. ``related_existing`` is an optional list of (ki_id, title)
    pairs to attach to; pass an empty list when the cluster has no
    pre-existing canonicals.
    """
    if not candidates:
        raise ValueError("build_cluster_prompt requires at least one candidate")

    intro = (
        "You are deciding which features in a cosine-similar CLUSTER describe "
        "the SAME end-user capability and should consolidate into one canonical "
        "feature. The cluster's first member is the proposed CANONICAL; the rest "
        "are candidate siblings that may or may not belong with it. Cluster "
        "members may come from different repos and different layers (frontend, "
        "backend, processor)."
    )

    canonical_block = _format_feature("CANONICAL", canonical_repo, canonical_feature)
    candidate_blocks = [
        _format_feature(f"CANDIDATE {i + 1}", repo, feat)
        for i, (repo, feat) in enumerate(candidates)
    ]

    sections = [
        intro,
        canonical_block,
        "CANDIDATES:\n" + "\n".join(candidate_blocks),
    ]
    if related_existing:
        existing_lines = [f"  - id={kid} title={title}" for kid, title in related_existing]
        sections.append(
            "RELATED EXISTING CANONICALS (consider folding the cluster into one of these):\n"
            + "\n".join(existing_lines)
        )
    sections.extend([DECISION_RULES.strip(), RESPONSE_FORMAT.strip()])
    return "\n\n".join(sections)
