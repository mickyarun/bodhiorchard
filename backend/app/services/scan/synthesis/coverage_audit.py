# SPDX-License-Identifier: MIT
# Copyright (C) 2026 Arun Rajkumar

"""Post-synthesis coverage audit.

The agentic synthesis pass exercises editorial judgement: Claude reads
the meta-community payload and decides which clusters become first-class
features. Anything it labels as noise lands in ``dropped_community_ids``
and never produces a row in ``synthesized_features`` — its files are
silently absent from the feature catalogue.

For most clusters that's correct (test, mock, migration, logging
fragments shouldn't be features). But singleton clusters labelled with
a short domain acronym — ``ais`` (Account Information Services), ``sca``
(Strong Customer Authentication), ``hl7`` (medical), ``crud``
(generated controllers) — are easy for Claude to misclassify as noise
when seen in isolation. The result: a domain with its own subdirectory
gets dismissed and never appears in features.

This module runs **after** the agentic pass and emits synthetic
"Uncategorised" features for cluster files that didn't make it into any
human-curated feature. Two guards keep the audit from creating noise:

1. **Path-segment evidence**: a cluster's label must appear as a literal
   directory segment in *all* of its files. ``ais`` only counts when
   files are under ``…/ais/…``; the tiny utility module that happened
   to share the name doesn't get promoted.
2. **Minimum file count**: a label-group must contribute at least
   ``MIN_AUDIT_FILES`` (3) unreferenced files across its clusters. One-
   file orphans get logged but not promoted — they really are noise.

The synthetic feature is tagged ``coverage:auto`` so the merge phase
and UI can distinguish "Claude wrote this" from "the audit filled in".

This module is generic across any codebase and any language. It uses
the cluster's own derived label (which came from path-token TF-IDF in
``code_indexer.labeling``) and the literal directory structure of the
repo. Zero hardcoded domain vocabulary.
"""

from __future__ import annotations

import json
import re
import uuid
from collections import defaultdict
from collections.abc import Iterable
from pathlib import PurePosixPath

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.mcp.synth_feature_writer import persist_synth_feature
from app.models.organization import Organization
from app.repositories.cluster_cache import ClusterCacheRepository
from app.repositories.synthesized_feature import SynthesizedFeatureRepository

logger = structlog.get_logger(__name__)


MIN_AUDIT_FILES = 5
"""Don't emit a synthetic feature for fewer than this many orphan files."""

MAX_AUDIT_FILES = 80
"""Hard cap on files in a single synthetic feature. Larger label-groups
truncate (sorted by path) — the audit is a safety net, not a complete
catalogue. If a domain has 300+ unreferenced files, the underlying
problem is "the synthesis pass missed an obvious domain", not "we need
to fan out".
"""

AUDIT_TAG = "coverage:auto"
"""Tag set on synthetic features so downstream merge / UI can tell them
apart from human-curated ones."""

# Programming-convention names that are universally infrastructure
# regardless of domain. Generic across languages — these are the
# directory / filename tokens that NEVER represent a business feature
# in their own right, even when they have their own subdirectory.
_INFRA_LABELS: frozenset[str] = frozenset(
    {
        # tests + mocks
        "test",
        "tests",
        "testing",
        "spec",
        "specs",
        "mock",
        "mocks",
        "fixture",
        "fixtures",
        "e2e",
        "stub",
        "stubs",
        # data-only artifacts
        "migration",
        "migrations",
        "seed",
        "seeds",
        "schema",
        "schemas",
        "type",
        "types",
        "interface",
        "interfaces",
        "enum",
        "enums",
        "entity",
        "entities",
        "dto",
        "dtos",
        "model",
        "models",
        "constant",
        "constants",
        # operational / build
        "config",
        "configs",
        "configuration",
        "settings",
        "log",
        "logs",
        "logging",
        "telemetry",
        "metric",
        "metrics",
        "build",
        "deploy",
        "ci",
        "cd",
        "docker",
        # generic helpers
        "util",
        "utils",
        "utility",
        "utilities",
        "helper",
        "helpers",
        "common",
        "shared",
        "lib",
        "libs",
        "library",
        "libraries",
        "core",
        "base",
        # framework conventions (universal)
        "controller",
        "controllers",
        "service",
        "services",
        "repository",
        "repositories",
        "handler",
        "handlers",
        "middleware",
        "middlewares",
        "decorator",
        "decorators",
        "view",
        "views",
        "page",
        "pages",
        "component",
        "components",
        "route",
        "routes",
        "api",
    }
)

# Path heuristics for layer assignment. Generic across language ecosystems.
_FRONTEND_EXT = re.compile(r"\.(vue|svelte|astro|tsx|jsx)$")
_FRONTEND_DIRS = re.compile(r"/(views|pages|components|composables|stores|layouts)/")
_BATCH_DIRS = re.compile(r"/(cron|jobs?|workers|batch|queue|tasks?|schedule)/")

_WORD_BOUNDARY = re.compile(r"[^a-z0-9]+")


async def audit_uncovered_clusters(
    db: AsyncSession,
    *,
    org: Organization,
    repo_id: uuid.UUID,
    scan_id: uuid.UUID,
    head_sha: str,
) -> int:
    """Emit a synthetic feature for each label-group of unreferenced clusters.

    Returns the number of synthetic features written. Safe to call when
    the synthesis pass already covered everything — this routine just
    finds zero orphans and returns 0.
    """
    if not head_sha:
        return 0

    cc_repo = ClusterCacheRepository(db, org_id=org.id)
    synth_repo = SynthesizedFeatureRepository(db, org_id=org.id)

    cached_clusters = await cc_repo.list_for_repo_sha(repo_id=repo_id, head_sha=head_sha)
    if not cached_clusters:
        return 0

    existing_features = await synth_repo.list_current_for_repo(repo_id=repo_id)
    referenced_files = _collect_referenced_files(existing_features)
    covered_labels = _labels_covered_by_features(existing_features)

    label_groups = _group_orphans_by_label(cached_clusters, referenced_files)
    if not label_groups:
        logger.info(
            "synthesis_coverage_audit_clean",
            repo_id=str(repo_id),
            head_sha=head_sha[:8],
            cached_clusters=len(cached_clusters),
        )
        return 0

    written = 0
    skipped_infra = 0
    skipped_covered = 0
    skipped_too_small = 0

    for label, clusters in label_groups.items():
        if label in _INFRA_LABELS:
            skipped_infra += 1
            continue
        if _label_already_covered(label, covered_labels):
            skipped_covered += 1
            continue
        unreferenced_files = _unique_files(clusters, exclude=referenced_files)
        if len(unreferenced_files) < MIN_AUDIT_FILES:
            skipped_too_small += 1
            continue
        capped = unreferenced_files[:MAX_AUDIT_FILES]
        await _emit_one_feature(
            db=db,
            org=org,
            repo_id=repo_id,
            scan_id=scan_id,
            label=label,
            clusters=clusters,
            files=capped,
            truncated=len(unreferenced_files) > MAX_AUDIT_FILES,
        )
        written += 1

    logger.info(
        "synthesis_coverage_audit_done",
        repo_id=str(repo_id),
        head_sha=head_sha[:8],
        synthetic_features_written=written,
        label_groups_considered=len(label_groups),
        skipped_infra=skipped_infra,
        skipped_already_covered=skipped_covered,
        skipped_too_small=skipped_too_small,
    )
    return written


# ── Internals ──────────────────────────────────────────────────────


def _collect_referenced_files(rows: Iterable) -> set[str]:
    """Union of files referenced by ANY current synth row.

    Each ``code_locations`` blob is ``{layer: [paths]}``.
    """
    referenced: set[str] = set()
    for row in rows:
        loc = row.code_locations
        if isinstance(loc, str):
            try:
                loc = json.loads(loc)
            except json.JSONDecodeError:
                continue
        if not isinstance(loc, dict):
            continue
        for files in loc.values():
            if isinstance(files, list):
                for f in files:
                    if isinstance(f, str) and f:
                        referenced.add(f)
    return referenced


def _labels_covered_by_features(rows: Iterable) -> set[str]:
    """Tokens that appear in any current feature's title or cluster names.

    The audit treats a label as 'covered' when it shows up in a feature
    Claude already wrote — preventing duplicate features for domains
    Claude already addressed (just under a different name).

    Returns a set of lowercase tokens (split on non-alphanumeric) so a
    feature titled "Public REST API Layer" registers the tokens
    ``{public, rest, api, layer}`` and a label like ``api`` is detected
    as covered.
    """
    covered: set[str] = set()
    for row in rows:
        title = (row.feature_title or "").lower()
        for tok in _WORD_BOUNDARY.split(title):
            if tok:
                covered.add(tok)
        names = row.cluster_names or []
        for name in names:
            for tok in _WORD_BOUNDARY.split(str(name).lower()):
                if tok:
                    covered.add(tok)
    return covered


def _label_already_covered(label: str, covered_tokens: set[str]) -> bool:
    """Return True if ``label`` (or any of its kebab parts) is already covered."""
    needle = label.lower()
    if needle in covered_tokens:
        return True
    return any(part and part in covered_tokens for part in needle.split("-"))


def _group_orphans_by_label(clusters: Iterable, referenced_files: set[str]) -> dict[str, list]:
    """Bucket clusters by ``label`` when at least one of their files is unreferenced.

    Path-segment evidence guard: only include a cluster if the cluster's
    label appears as a literal path segment in every contributing file.
    Otherwise the label is incidental (e.g. a 1-token tf-idf winner) and
    promoting it would be noise.
    """
    by_label: dict[str, list] = defaultdict(list)
    for c in clusters:
        files = list(c.files or [])
        if not files:
            continue
        unref = [f for f in files if f not in referenced_files]
        if not unref:
            continue
        if not _label_in_path_segments(c.label, files):
            continue
        by_label[c.label].append(c)
    return dict(by_label)


def _label_in_path_segments(label: str, files: Iterable[str]) -> bool:
    """Return True iff ``label`` appears as a directory segment in every file.

    The cluster's label is computed from path-token TF-IDF; we want to
    accept it as "domain evidence" only when it's anchored in the file
    system, not just a coincidence of filenames.
    """
    if not label:
        return False
    needle = label.lower()
    for f in files:
        parts = [p.lower() for p in PurePosixPath(f).parts]
        if needle not in parts:
            return False
    return True


def _unique_files(clusters: Iterable, *, exclude: set[str]) -> list[str]:
    """Union files across ``clusters``, preserving order, dropping ``exclude``."""
    seen: set[str] = set()
    out: list[str] = []
    for c in clusters:
        for f in c.files or []:
            if f in exclude or f in seen:
                continue
            seen.add(f)
            out.append(f)
    return out


async def _emit_one_feature(
    *,
    db: AsyncSession,
    org: Organization,
    repo_id: uuid.UUID,
    scan_id: uuid.UUID,
    label: str,
    clusters: list,
    files: list[str],
    truncated: bool,
) -> None:
    """Persist exactly one synthetic feature for an orphan label group.

    The audit deliberately emits one feature per label, never split.
    When the label-group is too large, we cap at ``MAX_AUDIT_FILES``
    and signal truncation in the description so reviewers know to look
    further.
    """
    title = _make_feature_title(label)
    description = _make_description(label, truncated=truncated)
    capabilities = _capabilities_from_files(files)
    source_ids = [c.cluster_id for c in clusters]
    loc = _classify_layers(files)
    await persist_synth_feature(
        db=db,
        org=org,
        repo_id=repo_id,
        feature_title=title,
        description=description,
        capabilities=capabilities,
        cluster_names=source_ids,
        code_locations=loc,
        tags=[AUDIT_TAG],
        knowledge_item_id=None,
        scan_id=scan_id,
    )
    await db.flush()


def _make_feature_title(label: str) -> str:
    """Render a Title-Cased feature title from a kebab-case label."""
    parts = [p for p in label.split("-") if p]
    if not parts:
        return f"Feature: {label or 'Uncategorised'}"
    return "Feature: " + " ".join(p[:1].upper() + p[1:] for p in parts)


def _make_description(label: str, *, truncated: bool) -> str:
    """Generic description that calls out the audit-origin so readers know."""
    base = (
        f"Files under the ``{label}`` domain that the synthesis pass did not "
        "categorise into a named feature. Auto-emitted by the post-synthesis "
        "coverage audit so the domain is at least represented in the "
        "feature catalogue. Review and refine: split into specific features, "
        "merge with an existing one, or rename."
    )
    if truncated:
        base += (
            f" NOTE: capped at {MAX_AUDIT_FILES} files; the underlying domain "
            "has more files than fit into a single feature row — likely "
            "indicates the synthesis pass missed a real domain."
        )
    return base


def _capabilities_from_files(files: list[str]) -> list[str]:
    """Derive 3-6 short capability bullets from filename stems.

    A filename like ``AisAccountAuthorization.ts`` becomes
    "Ais account authorization". We pick the most distinctive stems
    (longest, shortest first) to avoid duplicates from spec/test pairs.
    """
    stems: list[str] = []
    seen: set[str] = set()
    for f in files:
        stem = PurePosixPath(f).stem
        # Drop common test suffixes
        for suffix in (".spec", ".test"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
        if stem and stem not in seen:
            seen.add(stem)
            stems.append(stem)
        if len(stems) >= 6:
            break
    if not stems:
        return ["Files in this domain that need categorisation."]
    return [_humanise_stem(s) for s in stems]


def _humanise_stem(stem: str) -> str:
    """Convert ``AisAccountAuthorization`` → ``Ais account authorization``."""
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", stem)
    spaced = re.sub(r"[._\-]+", " ", spaced)
    spaced = " ".join(spaced.split())
    return spaced[:1].upper() + spaced[1:] if spaced else stem


def _classify_layers(files: list[str]) -> dict[str, list[str]]:
    """Map files to backend / frontend / batch / other by path heuristic."""
    layers: dict[str, list[str]] = defaultdict(list)
    for f in files:
        if _FRONTEND_EXT.search(f) or _FRONTEND_DIRS.search(f):
            layers["frontend"].append(f)
        elif _BATCH_DIRS.search(f):
            layers["batch"].append(f)
        else:
            layers["backend"].append(f)
    return dict(layers)


__all__ = [
    "AUDIT_TAG",
    "MAX_AUDIT_FILES",
    "MIN_AUDIT_FILES",
    "audit_uncovered_clusters",
]
