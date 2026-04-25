# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Prompt builders for the Claude subprocesses the scan pipeline launches.

Three prompts, one per Claude invocation point:

- ``build_synthesis_prompt`` — per-repo feature synthesis. Drives
  ``phase_b2_synthesis``'s loop over the cluster queue. Claude calls
  ``write_feature_registry`` for each business feature it identifies.
- ``build_direct_scan_prompt`` — fallback for small repos where
  GitNexus found zero clusters. Claude scans the file tree directly.
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
    """Build prompt for repos where GitNexus found no clusters.

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
    features: list[dict],
    unlinked_repos: list[dict] | None = None,
) -> str:
    """Build a prompt for cross-repo feature merging.

    Lists all features with their repo names and tags. The LLM calls
    ``merge_features`` for groups that represent the same business
    capability across repos.

    Also lists repos whose code wasn't clustered (e.g. small frontend
    repos) so the LLM can link them to existing features by name.

    Args:
        features: List of dicts with keys: title, repo_names, tags.
        unlinked_repos: Repos with 0 clusters — include their file
            listing so the LLM can link them to features.

    Returns:
        Prompt string for Claude Code CLI.
    """
    lines = []
    for i, f in enumerate(features, 1):
        repos = ", ".join(f["repo_names"]) if f["repo_names"] else "unlinked"
        tags = ", ".join(f.get("tags") or [])
        lines.append(f'{i}. "{f["title"]}" ({repos}) — {tags}')

    feature_list = "\n".join(lines)

    unlinked_section = ""
    if unlinked_repos:
        repo_lines = []
        for repo in unlinked_repos:
            files = ", ".join(repo["files"][:20])
            repo_lines.append(f"- **{repo['name']}**: {files}")
        unlinked_section = f"""

## Repos with no features yet

These repos were scanned but produced no features (too small for clustering).
Link them to existing features if their code matches:

{chr(10).join(repo_lines)}
"""

    return f"""You are merging duplicate features across repositories.

## Features

{feature_list}
{unlinked_section}
## Instructions

1. Look for features that represent the SAME business capability but exist
   in different repos (or have slightly different names). Call `merge_features`
   to consolidate them.

2. For repos listed under "Repos with no features yet", if their files clearly
   belong to an existing feature (e.g. a frontend repo with auth views matches
   "Authentication"), call `merge_features` with that repo added to repo_names.

Parameters for merge_features:
- keep_title: The most descriptive title from the group (exact match required)
- merge_titles: The other titles to merge into it (will be deactivated)
- repo_names: ALL repository names this feature belongs to

Rules:
- Only merge features that are clearly the same domain
- Do NOT merge features that are merely related (e.g. "Billing" and "Payments" are separate)
- If no duplicates or links exist, you are done — do nothing"""
