# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Stage 2 — Drop infra/test/config communities.

Two passes; a community is dropped if EITHER matches:

    Pass A: ``heuristic_label`` matches a regex in ``label_patterns``.
    Pass B: ≥ ``test_file_threshold`` of its sampled files match any
            regex in ``file_path_patterns``.

Pass B catches test communities whose label hides their nature — e.g. a
community labelled ``PaymentProcessor`` whose members are all ``*.test.ts``.
Without it we'd ship those into synthesis and Claude would invent a
"Payment Processor" feature that's actually just the test suite.

Each dropped community is annotated with ``drop_reason`` (label-match,
file-path-match, or both) so the UI can show *why*.
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from app.schemas.scan import Community
from app.services.scan._async_compute import to_thread_with_metric
from app.services.scan.stages import StageContext, StageOutput
from app.services.scan.stages._skip import maybe_skipped_for_ingest

logger = structlog.get_logger(__name__)


# Compiled at import-time — cheap, and one process-wide cache is fine
# since the regex strings are static defaults. Per-run overrides compile
# inside ``_compile_patterns``.
#
# Each pattern uses the ``(?i)`` inline flag so it matches both the
# legacy PascalCase ``heuristic_label`` (``Migration``, ``Tests``) and
# the lowercase kebab labels emitted by ``code_indexer.label_cluster``
# (``migration``, ``tests``, ``feature-flags``). Without it the
# label-match pass silently does nothing on graphify-derived labels.
DEFAULT_LABEL_PATTERNS: tuple[str, ...] = (
    r"(?i)^(Test|Tests|Testing|Mock|Fixture|Spec|E2E)",
    r"(?i)^(Config|Configuration|Settings)",
    r"(?i)^(Logging|Log|Telemetry|Metrics)",
    r"(?i)^(Migration|Schema|Seed)",
    r"(?i)^(CI|CD|Build|Deploy|Docker)",
    r"(?i)^(Type|Types|Interface)$",
)

DEFAULT_FILE_PATH_PATTERNS: tuple[str, ...] = (
    r"/tests?/",
    r"/__tests__/",
    r"/spec/",
    r"\.test\.(ts|tsx|js|jsx|py|go|java|kt|cs|rb)$",
    r"\.spec\.(ts|tsx|js|jsx|py|go|java|kt|cs|rb)$",
    r"_test\.(go|py)$",
    r"/testdata/",
    r"/fixtures?/",
    r"/mocks?/",
    r"/__mocks__/",
    r"conftest\.py$",
)

DEFAULT_TEST_FILE_THRESHOLD = 0.7


async def run(
    ctx: StageContext,
    communities: list[Community],
    config: dict[str, Any],
) -> StageOutput:
    """Drop infra/test communities. ``communities`` flows in from Stage 1."""
    if (
        skipped := maybe_skipped_for_ingest(config, io_label="communities → kept (non-infra)")
    ) is not None:
        return skipped
    label_patterns = config.get("label_patterns") or list(DEFAULT_LABEL_PATTERNS)
    file_path_patterns = config.get("file_path_patterns") or list(DEFAULT_FILE_PATH_PATTERNS)
    threshold = float(config.get("test_file_threshold", DEFAULT_TEST_FILE_THRESHOLD))

    label_res = _compile_patterns(label_patterns)
    file_res = _compile_patterns(file_path_patterns)

    kept, dropped = await to_thread_with_metric(
        "scan.filter_infra.classify",
        _classify_communities,
        communities,
        label_res,
        file_res,
        threshold,
    )

    extras: dict[str, Any] = {
        "input_count": len(communities),
        "drop_reasons": _summarise_reasons(dropped),
        "label_patterns": label_patterns,
        "file_path_patterns": file_path_patterns,
        "test_file_threshold": threshold,
        "io_label": "communities → kept (non-infra)",
    }
    logger.info(
        "scan_filter_infra_done",
        repo=ctx.repo_name,
        kept=len(kept),
        dropped=len(dropped),
    )
    return StageOutput(communities=kept, dropped=dropped, extras=extras)


def _classify_communities(
    communities: list[Community],
    label_res: list[re.Pattern[str]],
    file_res: list[re.Pattern[str]],
    threshold: float,
) -> tuple[list[Community], list[Community]]:
    """Apply label + file-path regex passes to every community.

    Pure-Python; runs inside ``asyncio.to_thread`` because the matrix
    is O(communities × files × patterns) and dominates the stage on
    large repos.
    """
    kept: list[Community] = []
    dropped: list[Community] = []
    for comm in communities:
        reasons: list[str] = []
        if comm.heuristic_label and any(p.search(comm.heuristic_label) for p in label_res):
            reasons.append("label-match")
        if comm.files:
            test_hits = sum(1 for f in comm.files if any(p.search(f) for p in file_res))
            ratio = test_hits / len(comm.files)
            if ratio >= threshold:
                reasons.append(f"file-path-match ({ratio:.0%} of {len(comm.files)} files)")
        if reasons:
            dropped.append(comm.model_copy(update={"drop_reason": "; ".join(reasons)}))
        else:
            kept.append(comm)
    return kept, dropped


def _compile_patterns(patterns: list[str]) -> list[re.Pattern[str]]:
    """Compile a list of regex strings, skipping invalid ones with a warning."""
    compiled: list[re.Pattern[str]] = []
    for raw in patterns:
        try:
            compiled.append(re.compile(raw, re.IGNORECASE))
        except re.error as exc:
            logger.warning("scan_filter_invalid_regex", pattern=raw, error=str(exc))
    return compiled


def _summarise_reasons(dropped: list[Community]) -> dict[str, int]:
    """Count how many communities were dropped for each reason category."""
    counts: dict[str, int] = {"label-match": 0, "file-path-match": 0, "both": 0}
    for comm in dropped:
        reason = comm.drop_reason or ""
        has_label = "label-match" in reason
        has_file = "file-path-match" in reason
        if has_label and has_file:
            counts["both"] += 1
        elif has_label:
            counts["label-match"] += 1
        elif has_file:
            counts["file-path-match"] += 1
    return counts
