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

"""Prompt builders for the Claude subprocesses the scan pipeline launches.

Three prompts, one per Claude invocation point:

- ``build_synthesis_prompt`` — per-repo feature synthesis. Drives
  ``phase_b2_synthesis``'s loop over the cluster queue. Claude calls
  ``write_feature_registry`` for each business feature it identifies.
- ``build_direct_scan_prompt`` — fallback for small repos where
  Code indexer found zero clusters. Claude scans the file tree directly.
- ``build_merge_prompt`` — global cross-repo dedup. Claude calls
  ``merge_features`` to consolidate same-domain features across repos.

Kept as pure functions (input → string) so they can be unit-tested
without the Claude subprocess plumbing. The orchestrator imports them;
phase modules invoke them when they need a prompt.
"""

from __future__ import annotations

_WRITE_FEATURE_DOCS = """      - feature_name: Human-readable name (e.g., "Card Payments")
      - description: 1-2 sentences of what this feature does in business terms
      - capabilities: 3-6 specific things this feature does
      - code_locations: Map layers to file paths, e.g.:
        {{"backend": ["src/services/card/"], "frontend": ["src/views/Pay.vue"]}}
        Layers: backend, frontend, batch (background jobs), other
      - tags: 2-5 lowercase search keywords"""

_GROUPING_RULES = """## Grouping Rules

- Group related functionality into a SINGLE feature
- Target broad domain-level features, not narrow per-file features
- Skip infrastructure (config, build, CI/CD, testing utilities)"""


def build_synthesis_prompt(
    repo_name: str,
    readme_overview: str,
    is_workspace: bool,
) -> str:
    """Build the Claude Code prompt for feature synthesis.

    Args:
        repo_name: Name of the repository being processed.
        readme_overview: First 2000 chars of the repo README.
        is_workspace: Whether this is a multi-repo workspace scan.
            Currently unused but kept in the signature for caller
            compatibility — a future change may diverge prompts when
            synthesising into a workspace with already-merged features.

    Returns:
        Prompt string for Claude Code CLI.
    """
    del is_workspace  # accepted for caller compat; not currently consumed
    repo_name_line = f'      - repo_name: "{repo_name}"'
    return f"""You are synthesizing human-readable feature descriptions \
for repository "{repo_name}".

README Overview:
{readme_overview[:2000]}

## Instructions

Follow this loop exactly:

1. Call `get_pending_features` to get the next batch of unprocessed clusters
2. If the response has `done: true`, you are finished — stop here
3. For each cluster in the batch:
   a. Read the cluster's key files to understand what the code does
   b. Skip infrastructure/utility clusters (logging, config, migrations, CI/CD)
   c. For real business features, call `write_feature_registry` with:
{_WRITE_FEATURE_DOCS}
      - source_clusters: Array containing the cluster name(s)
{repo_name_line}
4. Go back to step 1

{_GROUPING_RULES}

- When multiple clusters clearly belong to the same domain, combine them
  into one `write_feature_registry` call with all their code_locations merged.
- Target 8-15 features per repo. Prefer broader domain-level features
  over narrow per-function features.

Important: Process ALL clusters returned by get_pending_features before calling
it again. Do not call get_pending_features mid-batch."""


def build_direct_scan_prompt(
    repo_name: str,
    readme_overview: str,
    file_tree: str,
) -> str:
    """Build prompt for repos where Code indexer found no clusters.

    Claude scans the file structure directly to identify features instead of
    processing a cluster queue.

    Args:
        repo_name: Name of the repository being processed.
        readme_overview: First 2000 chars of the repo README.
        file_tree: Newline-separated list of source files.

    Returns:
        Prompt string for Claude Code CLI.
    """
    repo_name_line = f'      - repo_name: "{repo_name}"'
    return f"""You are scanning repository "{repo_name}" to identify business features.
This repo had no code clusters detected, so scan the file structure directly.

README Overview:
{readme_overview[:2000]}

## File Structure
{file_tree[:3000]}

## Instructions

1. Read the key source files to understand what the code does
2. Identify 3-8 business-level features (not infrastructure/utilities)
3. For each feature, call `write_feature_registry` with:
{_WRITE_FEATURE_DOCS}
      - source_clusters: ["direct_scan"]
{repo_name_line}

{_GROUPING_RULES}"""


def build_merge_prompt(
    new_features: list[dict],
    existing_canonicals: list[dict],
    unlinked_repos: list[dict] | None = None,
) -> str:
    """Build a two-section prompt for cross-repo feature merging.

    The merge step deduplicates the freshly-synthesised features from this
    scan (``new_features``) AND links them against canonical features
    persisted from prior scans (``existing_canonicals``). Each row carries
    a typed id prefix so the LLM can name a target unambiguously:
    ``[synth:<uuid>]`` for new rows, ``[ki:<uuid>]`` for existing canonicals.

    The LLM calls ``apply_feature_merge_plan`` (a single MCP tool) with a
    list of merge ops; each op names exactly one canonical id (either
    ``canonical_synth_id`` or ``canonical_knowledge_id``).

    Args:
        new_features: Synthesised features from this scan. Required keys:
            ``synth_id``, ``title``, ``repo_names``, ``tags``,
            ``cluster_names``, ``description``, ``capabilities``,
            ``code_locations``.
        existing_canonicals: Canonical features from prior scans. Required
            keys: ``knowledge_id``, ``title``, ``repo_names``,
            ``cluster_names``, ``summary``.
        unlinked_repos: Tracked repos that produced zero features (too
            small to cluster). Their files are surfaced so the LLM can
            link them to an existing feature via the op's ``repo_ids``.

    Returns:
        Prompt string for Claude Code CLI.
    """
    new_lines: list[str] = []
    for f in new_features:
        repos = ", ".join(f.get("repo_names") or []) or "unlinked"
        tags = ", ".join(f.get("tags") or [])
        clusters = ", ".join(f.get("cluster_names") or [])
        capabilities = "; ".join(f.get("capabilities") or [])
        code_locations = ", ".join(f.get("code_locations") or [])
        new_lines.append(
            f'- [synth:{f["synth_id"]}] "{f["title"]}" ({repos})\n'
            f"    tags: {tags}\n"
            f"    clusters: {clusters}\n"
            f"    description: {f.get('description', '')}\n"
            f"    capabilities: {capabilities}\n"
            f"    code_locations: {code_locations}"
        )
    new_section = "## NEW features\n\n" + ("\n".join(new_lines) if new_lines else "(none)")

    existing_section = ""
    if existing_canonicals:
        ex_lines: list[str] = []
        for f in existing_canonicals:
            repos = ", ".join(f.get("repo_names") or []) or "unlinked"
            clusters = ", ".join(f.get("cluster_names") or [])
            ex_lines.append(
                f'- [ki:{f["knowledge_id"]}] "{f["title"]}" ({repos})\n'
                f"    clusters: {clusters}\n"
                f"    summary: {f.get('summary', '')}"
            )
        existing_section = "## EXISTING canonicals\n\n" + "\n".join(ex_lines) + "\n\n"

    unlinked_section = ""
    if unlinked_repos:
        repo_lines = [
            f"- **{repo['name']}**: {', '.join(repo['files'][:20])}" for repo in unlinked_repos
        ]
        unlinked_section = (
            "## Repos with no features yet\n\n"
            "These repos were scanned but produced no features (too small for "
            "clustering). Attach them to a merge op via ``repo_ids`` if their "
            "code clearly belongs to an existing feature.\n\n" + "\n".join(repo_lines) + "\n\n"
        )

    return f"""You are merging duplicate features across repositories.

{existing_section}{new_section}

{unlinked_section}## Instructions

Call ``apply_feature_merge_plan`` once with a list of merge ops. Each op
collapses a group of duplicates onto a single canonical row.

For every op, set **exactly one of**:

- ``canonical_synth_id``: pick a NEW row's ``synth_id`` (group of new
  features only — no existing canonical involved).
- ``canonical_knowledge_id``: pick an EXISTING row's ``knowledge_id``
  (group includes at least one existing canonical — the new rows merge
  into it).

Op fields:

- ``canonical_synth_id`` OR ``canonical_knowledge_id`` (XOR — never both)
- ``absorb_synth_ids``: list of NEW ``synth_id`` values absorbed into the
  canonical
- ``absorb_knowledge_ids`` (optional): list of EXISTING ``knowledge_id``
  values absorbed into the canonical (use sparingly — only when two
  prior canonicals are clearly the same feature)
- ``repo_ids`` (optional): tracked-repo ids to attach to this canonical
  (use for unlinked repos whose code matches the feature)
- ``rationale``: one short sentence on why these are the same feature

Rules:
- Only merge features that are clearly the same business capability
- Do NOT merge features that are merely related ("Billing" and "Payments"
  are separate)
- If no duplicates or links exist, return an empty ``ops`` list — done"""
