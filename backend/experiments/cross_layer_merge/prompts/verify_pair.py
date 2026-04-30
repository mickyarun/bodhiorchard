# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

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
1. SAME-CAPABILITY = the two features cover the same end-user goal
   across layers (e.g. frontend "Magic Link sign-in form" + backend
   "Magic link token verification" → same goal: sign-in via magic link).
   These should be MERGED into one canonical feature.

2. RELATED-BUT-DIFFERENT = the features compose into the same flow but
   are independently useful or could be replaced separately
   (e.g. "Send magic-link email" vs "Verify magic-link token" — both
   parts of magic-link auth, but distinct technical capabilities that
   could be implemented by different services). DO NOT merge.

3. DIFFERENT = no shared end-user goal. DO NOT merge.

When in doubt, prefer NOT to merge — false merges are harder to
recover from than missed merges.

Cross-layer signal hierarchy (strongest → weakest):
- An HTTP route on the frontend hitting an endpoint that the backend
  candidate handles → very strong evidence of SAME-CAPABILITY.
- Tags overlap (e.g. both have "auth", "payments") → moderate.
- Title or description string-overlap → weak (vocabulary differs across
  layers; do not rely on it alone).
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
