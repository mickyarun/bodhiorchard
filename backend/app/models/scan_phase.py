# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Enums describing scan pipeline phases and their lifecycle state.

Centralises the vocabulary used by ``scan_phase_checkpoints`` rows, the
``/api/v1/skills/scan/*`` resume endpoints, and the frontend timeline.
Keeping this in its own module prevents circular imports between the
pipeline services and the checkpoint model.

See ``BODHIORCHARD-ARCHITECTURE.md §18.12`` for the role of each phase.
"""

from enum import StrEnum


class ScanPhase(StrEnum):
    """The 11 phases of a repository scan.

    Enum *values* are stable identifiers persisted in the database and
    exposed in the HTTP API. The legacy A..G codes live in comments
    only, for grep-ability with older runbooks and logs.
    """

    MODE_DETECTION = "mode_detection"  # was A
    CODE_INDEX = "code_index"  # was B
    REPO_SETUP = "repo_setup"  # was B1
    STALE_CLEANUP = "stale_cleanup"  # was D  (incremental only)
    SKILL_EXTRACTION = "skill_extraction"  # was E
    DESIGN_SYSTEM_EXTRACT = "design_system_extract"  # was E1b
    FEATURE_SYNTHESIS = "feature_synthesis"  # was B2
    EXTRACT_ROUTES = "extract_routes"  # backend repo HTTP-route cache writer
    SKILL_REMAP = "skill_remap"  # was E2
    FEATURE_MERGE = "feature_merge"  # was B3 (legacy; phase removed)
    BACKEND_LINK = "backend_link"  # cross-layer frontend↔backend link writer
    EMBEDDING_BACKFILL = "embedding_backfill"  # was F
    PERSIST_RESULTS = "persist_results"  # was G


class PhaseScope(StrEnum):
    """Whether a phase runs once per repo or once per scan."""

    PER_REPO = "per_repo"
    GLOBAL = "global"


class CheckpointStatus(StrEnum):
    """Lifecycle state of a single ``scan_phase_checkpoints`` row."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


class ScanErrorCode(StrEnum):
    """Classified failure reasons set on a failed checkpoint.

    Producers (``classify_scan_error``) and consumers (API schema,
    frontend timeline) share this vocabulary so the UI can render
    actionable hints without string-matching raw exception messages.
    """

    MAX_TURNS = "max_turns"
    CLAUDE_SUBPROCESS = "claude_subprocess"
    MCP_ERROR = "mcp_error"
    TIMEOUT = "timeout"
    ORPHAN_FEATURE = "orphan_feature"
    UNMATCHED_AUTHORS = "unmatched_authors"
    EXCEPTION = "exception"


PHASE_SCOPE: dict[ScanPhase, PhaseScope] = {
    ScanPhase.MODE_DETECTION: PhaseScope.PER_REPO,
    ScanPhase.CODE_INDEX: PhaseScope.PER_REPO,
    ScanPhase.REPO_SETUP: PhaseScope.PER_REPO,
    ScanPhase.STALE_CLEANUP: PhaseScope.PER_REPO,
    ScanPhase.SKILL_EXTRACTION: PhaseScope.PER_REPO,
    ScanPhase.DESIGN_SYSTEM_EXTRACT: PhaseScope.PER_REPO,
    ScanPhase.FEATURE_SYNTHESIS: PhaseScope.PER_REPO,
    ScanPhase.EXTRACT_ROUTES: PhaseScope.PER_REPO,
    ScanPhase.SKILL_REMAP: PhaseScope.GLOBAL,
    ScanPhase.FEATURE_MERGE: PhaseScope.GLOBAL,
    ScanPhase.BACKEND_LINK: PhaseScope.GLOBAL,
    ScanPhase.EMBEDDING_BACKFILL: PhaseScope.GLOBAL,
    ScanPhase.PERSIST_RESULTS: PhaseScope.GLOBAL,
}


# Phases whose output is a pure function of the repo HEAD sha and
# therefore qualify for cross-scan reuse: when a later scan sees the
# same ``(org_id, repo_id, phase, sha_at_run)``, it copies the prior
# checkpoint's payload instead of re-running the work. Mutating phases
# (synthesis, merge, persist) are never in this set.
# CODE_INDEX is intentionally NOT in this set: its phase body
# populates the per-repo loop's cluster closure that
# ``build_pending_synthesis`` reads downstream. Cross-scan reuse skips
# the body and leaves that closure empty, which silently produces
# zero pending synthesis tasks → zero features. (Discovered live on
# scan ``f1373d55-…``.) The code indexer has its own SHA-based
# cache (cluster_cache + repo_graph_cache) so re-running per scan is cheap.
SHA_REUSABLE_PHASES: frozenset[ScanPhase] = frozenset(
    {
        ScanPhase.SKILL_EXTRACTION,
        ScanPhase.DESIGN_SYSTEM_EXTRACT,
    }
)


TERMINAL_CHECKPOINT_STATUSES: frozenset[CheckpointStatus] = frozenset(
    {CheckpointStatus.DONE, CheckpointStatus.FAILED, CheckpointStatus.SKIPPED}
)


def is_per_repo(phase: ScanPhase) -> bool:
    """Return True if the phase runs once per repo (vs once per scan)."""
    return PHASE_SCOPE[phase] is PhaseScope.PER_REPO
