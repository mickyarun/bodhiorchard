# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Synthesis prompt builder for the v2 pipeline.

Direct-payload approach: the prompt embeds the full reduced
meta-community list as JSON so Claude doesn't need an MCP queue
round-trip per batch. Claude reads this list once and produces
features, calling ``write_synthesis_feature`` per feature.
"""

from __future__ import annotations

import json
from typing import Any

from app.schemas.scan import Community

# Cap the readme excerpt — anything beyond ~2000 chars adds noise
# without helping Claude name features.
README_CHAR_CAP = 2000

# Files-per-community cap inside the synthesis payload. Smaller than
# the reduction-stage cap (which fed filter_infra) because Claude
# triages from labels + symbol_count and only needs a few files to
# disambiguate. 15 keeps the payload around 9-15 K tokens for a
# 100-community repo.
DEFAULT_FILES_PER_COMMUNITY = 15


def build_synthesis_prompt(
    *,
    repo_name: str,
    readme: str,
    communities: list[Community],
    files_per_community: int = DEFAULT_FILES_PER_COMMUNITY,
    scan_id: str | None = None,
    repo_id: str | None = None,
) -> str:
    """Render the synthesis prompt as a string.

    The prompt:
    * pins the repo name and a trimmed readme
    * embeds the reduced meta-community list as JSON
    * spells out the source_count + cohesion heuristics that the v1
      pipeline never gave Claude
    * tells Claude to call ``write_synthesis_feature`` per feature

    When ``scan_id`` and ``repo_id`` are provided, the prompt instructs
    Claude to pass them back in every ``write_synthesis_feature`` call —
    that way persistence binds to the exact scan + repo this run owns,
    instead of inferring it from a global active-scan lookup that can
    race or evict mid-run. Omitted only for sandbox/dry-run callers.
    """
    payload = _payload_for_communities(communities, files_per_community)
    payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    readme_excerpt = readme[:README_CHAR_CAP] if readme else "(no readme available)"
    scan_context = _scan_context_block(scan_id=scan_id, repo_id=repo_id)
    return _PROMPT_TEMPLATE.format(
        repo_name=repo_name,
        readme=readme_excerpt,
        community_count=len(payload),
        community_payload=payload_json,
        scan_context=scan_context,
    )


def _scan_context_block(*, scan_id: str | None, repo_id: str | None) -> str:
    """Render the scan-context preamble. Empty when ids weren't threaded."""
    if not scan_id or not repo_id:
        return ""
    return (
        "\n## Scan context (pass these back verbatim)\n"
        f"- ``scan_id``: {scan_id}\n"
        f"- ``repo_id``: {repo_id}\n"
        "Include both fields in **every** ``write_synthesis_feature`` call so "
        "the backend persists each feature against this exact scan and repo. "
        "Do not invent or alter these values.\n"
    )


def _payload_for_communities(
    communities: list[Community],
    files_per_community: int,
) -> list[dict[str, Any]]:
    """Trim ``Community`` objects to the JSON shape Claude consumes."""
    payload: list[dict[str, Any]] = []
    for c in communities:
        if c.drop_reason:
            continue
        payload.append(
            {
                "community_id": c.community_id or "",
                "label": c.label,
                "symbol_count": c.symbol_count,
                "source_count": max(1, len(c.source_community_ids)),
                "cohesion": _round_or_none(c.cohesion),
                "files": list(c.files[:files_per_community]),
            }
        )
    return payload


def _round_or_none(value: float | None) -> float | None:
    """Round cohesion to 3dp for prompt readability; preserve None."""
    return None if value is None else round(value, 3)


_PROMPT_TEMPLATE = """You are synthesising features for repository "{repo_name}".

README overview:
{readme}
{scan_context}
You will receive {community_count} reduced meta-communities. They have already
been deduplicated, infra-filtered, and hierarchically grouped. Your job is to
compile **every meaningful user-visible feature** in this repository — do not
miss any. There is no cap on the number of features; produce as many or as
few as the codebase genuinely warrants. If a community represents a real
capability, it deserves a feature.

Reduced meta-communities (JSON):
{community_payload}

## How to read each community
- ``label`` — composite name like "Payments + Links + Invoice". A "+" means
  several Leiden fragments were merged; the label captures the top three.
- ``symbol_count`` — total symbols across the merged fragments.
- ``source_count`` — how many original Leiden fragments were merged. Higher
  numbers signal a broad domain that may map to multiple features.
- ``cohesion`` — symbol-weighted average of the merged fragments' cohesion.
  ``null`` means GitNexus had no cohesion data.
- ``files`` — up to 15 representative file paths.

## Heuristics
- ``source_count > 5`` AND ``cohesion < 0.3`` → composite cluster. Likely
  multiple features inside; split it. Read a few files to decide the split.
- ``source_count == 1`` AND ``cohesion > 0.7`` → tight single feature. Keep
  it as one feature; do not collapse it into a sibling.
- Test / Mock / Migration / Logging-style labels should already be filtered,
  but if any leak through, mark them as ``dropped_community_ids`` rather
  than synthesising features for them.
- Prefer broader domain-level features over narrow per-function ones, but
  never drop a real capability just to keep the count down.

## Process
1. Use the Read tool to inspect a handful of files for any cluster you're
   unsure about.
2. Group composites where appropriate (high source_count + low cohesion);
   split them where they cover distinct capabilities.
3. For each feature, call ``write_synthesis_feature`` with:
   - ``name``: human-readable name e.g. "Card Payments"
   - ``description``: 1-2 sentence business description
   - ``source_community_ids``: array of ``community_id`` values (the ids you
     just received) that fed this feature
   - ``dropped_community_ids``: array of ``community_id`` values you decided
     not to use (because they're noise/utility)
   - ``code_locations``: object mapping layer to file paths,
     e.g. {{"backend": ["src/services/payments/..."]}}
   - ``repo_name``: "{repo_name}"
   - ``scan_id`` and ``repo_id`` from the *Scan context* block above (when
     provided). These bind the persisted feature to this exact scan run.
4. Stop when every community is either in ``source_community_ids`` of some
   feature OR in ``dropped_community_ids`` of some feature. Completeness
   matters: do not leave real capabilities unassigned.
"""
