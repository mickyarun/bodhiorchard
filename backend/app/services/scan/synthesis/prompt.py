# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Synthesis prompt builder for the pipeline.

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

# Files-per-community cap inside the synthesis payload. The path-segment
# vocabulary in these files is what Claude has to lean on when writing
# descriptions — too few files and 3-5 sentence descriptions become
# guesswork. 25 keeps the payload around 15-22 K tokens for a 100-
# community repo, still well inside the prompt-cache budget.
DEFAULT_FILES_PER_COMMUNITY = 25


def build_synthesis_prompt(
    *,
    repo_name: str,
    readme: str,
    communities: list[Community],
    files_per_community: int = DEFAULT_FILES_PER_COMMUNITY,
    repo_id: str | None = None,
) -> str:
    """Render the synthesis prompt as a string.

    The prompt:
    * pins the repo name and a trimmed readme
    * embeds the reduced meta-community list as JSON
    * spells out the source_count + cohesion heuristics that the v1
      pipeline never gave Claude
    * tells Claude to call ``write_synthesis_feature`` per feature

    When ``repo_id`` is provided, the prompt instructs Claude to echo it
    back in every ``write_synthesis_feature`` call — that way the
    backend handler doesn't have to re-resolve the repo by name and the
    binding survives renames mid-scan. Omitted only for sandbox/dry-run
    callers.
    """
    payload = _payload_for_communities(communities, files_per_community)
    payload_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    readme_excerpt = readme[:README_CHAR_CAP] if readme else "(no readme available)"
    scan_context = _scan_context_block(repo_id=repo_id)
    return _PROMPT_TEMPLATE.format(
        repo_name=repo_name,
        readme=readme_excerpt,
        community_count=len(payload),
        community_payload=payload_json,
        scan_context=scan_context,
    )


def _scan_context_block(*, repo_id: str | None) -> str:
    """Render the scan-context preamble. Empty when no ``repo_id`` was threaded."""
    if not repo_id:
        return ""
    return (
        "\n## Scan context (pass this back verbatim)\n"
        f"- ``repo_id``: {repo_id}\n"
        "Include this field in **every** ``write_synthesis_feature`` call so "
        "the backend binds each feature to this exact repo. Do not invent "
        "or alter the value.\n"
    )


def _payload_for_communities(
    communities: list[Community],
    files_per_community: int,
) -> list[dict[str, Any]]:
    """Trim ``Community`` objects to the JSON shape Claude consumes.

    The ``cluster_ids`` field surfaces the meta's constituent
    ``source_community_ids`` — the actual ``cluster_cache`` row keys
    (e.g. ``c22``, ``c39``). Claude is asked to echo these back in
    every ``write_synthesis_feature`` call so the server-side handler
    can expand ``code_locations`` with every file from every chosen
    cluster, closing the gap where Claude lists only a few
    representative files per feature.
    """
    payload: list[dict[str, Any]] = []
    for c in communities:
        if c.drop_reason:
            continue
        cluster_ids: list[str] = list(c.source_community_ids or [])
        if c.community_id and c.community_id not in cluster_ids:
            # Raw clusters that didn't go through hierarchical merge
            # have ``community_id`` set but ``source_community_ids``
            # empty. Surface the id so the auto-expand still works.
            cluster_ids = [c.community_id, *cluster_ids]
        payload.append(
            {
                "community_id": c.community_id or "",
                "cluster_ids": cluster_ids,
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
  several fragments were merged; the label captures the top three.
- ``cluster_ids`` — the underlying cluster_cache row ids (e.g. ``["c22",
  "c39"]``). **Pass these back verbatim** in ``source_community_ids`` so
  the server can expand ``code_locations`` with every file in those
  clusters automatically — you don't need to enumerate file paths.
- ``symbol_count`` — total symbols across the merged fragments.
- ``source_count`` — how many original fragments were merged. Higher
  numbers signal a broad domain that may map to multiple features.
- ``cohesion`` — symbol-weighted average of the merged fragments' cohesion.
  ``null`` means cohesion data was unavailable.
- ``files`` — up to 25 representative file paths (sample). The recurring
  path-segments across these files are the strongest signal for the
  feature's domain noun.

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

## Naming discipline (titles must reflect the dominant cluster domain)
The ``name`` you pass to ``write_synthesis_feature`` is what users see. It
must describe the **domain** carried by the ``cluster_ids`` you listed in
``source_community_ids`` — not a single endpoint, file, or sub-component
inside that domain.

- Read the cluster ``label`` and the ``files`` sample. The recurring
  path-segment in the file paths (e.g. a folder name appearing across
  most files) IS the domain.
- If two ``cluster_ids`` share the same label, the feature title must
  name that shared domain — not one endpoint, route, or controller
  file that happens to live inside it.
- If you cannot name a single domain that covers the cluster files, the
  cluster is composite — split it into multiple features rather than
  picking a misleading single title.

**Worked example.** A meta has ``cluster_ids: ["c22", "c39"]``, both
labelled ``ais``, with files like ``src/controllers/api/ais/AisSdk.ts``,
``src/services/ais/AisService.ts``. The recurring path-segment is ``ais``.

- BAD: ``"App Config Controller"`` — picks one file (``AppConfigController``)
  that happens to live next door; ignores the dominant ``ais`` segment.
- BAD: ``"AIS Controller"`` — names the layer (controller), not the domain.
- GOOD: ``"AIS / Account Information Services"`` — names the domain
  carried by both clusters.

## Process
1. Use the Read tool to inspect a handful of files for any cluster you're
   unsure about.
2. Group composites where appropriate (high source_count + low cohesion);
   split them where they cover distinct capabilities.
3. For each feature, call ``write_synthesis_feature`` with:
   - ``name``: human-readable name (see *Naming discipline* above).
   - ``description``: 3-5 sentence business description covering: (a) what
     the feature does in user/business terms; (b) who or what triggers it
     (user action, scheduled job, inbound webhook, sibling service call);
     (c) the data it consumes and produces; (d) any sibling layers or
     services it interacts with. Use the canonical domain noun for the
     capability — the same noun that appears in UI labels, API route
     segments, and storage table names — because that shared vocabulary
     is what lets cross-repository merging recognise the same capability
     across layers.
   - ``source_community_ids``: array of **``cluster_ids``** values (the
     ``c<N>`` ids from the ``cluster_ids`` field of the metas you used).
     The server expands ``code_locations`` from these — passing them
     accurately is what makes file coverage complete. If you used a
     meta with ``cluster_ids: ["c22", "c39"]``, list both.
   - ``dropped_community_ids``: array of ``cluster_id`` values you decided
     not to use (because they're noise/utility).
   - ``code_locations``: object mapping layer to file paths,
     e.g. {{"backend": ["src/services/payments/..."]}}. **Server-side,
     this gets unioned with every file from each cluster you listed in
     ``source_community_ids`` — you only need to add files the cluster
     samples didn't already show.**
   - ``repo_name``: "{repo_name}"
   - ``repo_id`` from the *Scan context* block above (when provided).
     This binds the persisted feature to this exact repo and skips a
     name-resolution round-trip.
4. Stop when every community is either in ``source_community_ids`` of some
   feature OR in ``dropped_community_ids`` of some feature. Completeness
   matters: do not leave real capabilities unassigned.
"""
