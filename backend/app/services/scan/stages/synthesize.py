# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Stage 8 — Synthesise features from the reduced meta-communities.

Inputs the kept set from Stage 7 (``top_n``) and an optional readme.
Builds a direct-payload prompt, hands it to a ``SynthesisEngine``,
and lets Claude call the new ``write_synthesis_feature`` MCP tool
inline as it produces each feature. This stage is purely an orchestrator
— the persistence happens server-side via that MCP handler.

After Claude returns, the stage queries the v2 persistence layer to
count how many features landed for this repo+sha and reports counts
back in ``extras``.

Config keys (all optional, defaults from ``synthesis/runner.py``):
    - ``model``: Claude model identifier (default ``claude-sonnet-4-6``)
    - ``max_turns``: Claude tool-call budget (default 40)
    - ``timeout_seconds``: subprocess timeout (default 300)
    - ``files_per_community``: cap inside the synthesis payload
      (default 15 — see ``synthesis/prompt.py``)
    - ``dry_run``: when True, build the prompt and report stats but do
      not call Claude. Useful for token-cost previewing.
    - ``readme``: free-form repo overview to embed in the prompt; the
      caller can hand in the README contents or any other context.
    - ``mcp_backend_url`` / ``mcp_token``: forwarded into ``run_claude_code``
      so the spawned subprocess can call ``write_synthesis_feature`` back
      to this server. Required when ``dry_run`` is False.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import structlog

from app.scan.session import with_session
from app.schemas.scan import Community
from app.services.scan.stages import StageContext, StageOutput
from app.services.scan.stages._skip import stage_output_for_skip
from app.services.scan.stages._skip_predicates import should_skip_feature_synthesis
from app.services.scan.stages._v2_context import resolve_v2_context
from app.services.scan.synthesis.coverage_audit import audit_uncovered_clusters
from app.services.scan.synthesis.prompt import (
    DEFAULT_FILES_PER_COMMUNITY,
    build_synthesis_prompt,
)
from app.services.scan.synthesis.runner import (
    DEFAULT_MAX_TURNS,
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SECONDS,
    ClaudeCodeEngine,
    SynthesisEngine,
    SynthesisRequest,
)

logger = structlog.get_logger(__name__)


async def run(
    ctx: StageContext,
    communities: list[Community],
    config: dict[str, Any],
) -> StageOutput:
    """Drive Claude through one synthesis pass over the reduced communities."""
    v2 = resolve_v2_context(config)
    repo_id_raw = config.get("v2_repo_id")
    if v2 is not None and repo_id_raw is not None:
        repo_id = uuid.UUID(str(repo_id_raw))
        async with with_session(v2.org_id) as db:
            decision = await should_skip_feature_synthesis(
                db,
                org_id=v2.org_id,
                repo_id=repo_id,
                repo_path=ctx.repo_path,
                full_rescan=bool(config.get("v2_full_rescan", False)),
            )
        if decision.skip:
            return stage_output_for_skip(decision, io_label="communities → features")
    if not communities:
        return StageOutput(
            communities=[],
            dropped=[],
            extras={"reason": "no input", "feature_count": 0},
        )

    files_per = int(config.get("files_per_community", DEFAULT_FILES_PER_COMMUNITY))
    model = str(config.get("model", DEFAULT_MODEL))
    max_turns = int(config.get("max_turns", DEFAULT_MAX_TURNS))
    timeout_seconds = int(config.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    readme = str(config.get("readme", ""))
    dry_run = bool(config.get("dry_run", False))

    # Thread the v2 scan + repo ids into the prompt so Claude echoes them
    # back in every ``write_synthesis_feature`` call. This replaces the
    # backend-side ``get_active_scan_for_org`` heuristic with explicit
    # binding — no race against late MCP calls or stale-eviction edges.
    scan_id_str = config.get("v2_scan_id")
    repo_id_str = config.get("v2_repo_id")
    prompt = build_synthesis_prompt(
        repo_name=ctx.repo_name,
        readme=readme,
        communities=communities,
        files_per_community=files_per,
        scan_id=str(scan_id_str) if scan_id_str else None,
        repo_id=str(repo_id_str) if repo_id_str else None,
    )
    extras: dict[str, Any] = {
        "model": model,
        "max_turns": max_turns,
        "timeout_seconds": timeout_seconds,
        "files_per_community": files_per,
        "prompt_chars": len(prompt),
        "estimated_input_tokens": len(prompt) // 4,
        "community_count": len(communities),
        "dry_run": dry_run,
        # The synthesize stage passes its input ``communities`` through
        # unchanged (so downstream stages can still use them) but the
        # real output is per-feature MCP writes. Counts here drive the
        # chip popover's "in → kept" reduction line; the actual feature
        # titles render via ``produced_features`` injected by the
        # serialiser (see ``scans_serialize._render_step``).
        "input_count": len(communities),
        # Default kept_count to 0; the post-run hook below replaces it
        # with the live synthesized-feature count for this repo+scan.
        "kept_count": 0,
        "io_label": "communities → features",
    }

    if dry_run:
        logger.info(
            "scan_synthesize_dry_run",
            repo=ctx.repo_name,
            community_count=len(communities),
            prompt_chars=len(prompt),
        )
        return StageOutput(communities=communities, dropped=[], extras=extras)

    # Skip cleanly when MCP credentials weren't threaded by the caller.
    # Raising here would mark the whole repo run FAILED for what is
    # really a "synthesis not yet wired" scenario; the v2 page already
    # has features from prior scans persisted in knowledge_items.
    if not config.get("mcp_backend_url") or not config.get("mcp_token"):
        extras["skipped_cache"] = True
        extras["reason"] = "mcp_credentials_missing"
        extras["skipped_reason"] = "MCP credentials not configured"
        logger.warning(
            "scan_synthesize_skipped_no_mcp",
            repo=ctx.repo_name,
            community_count=len(communities),
        )
        return StageOutput(communities=communities, dropped=[], extras=extras)

    engine = _resolve_engine(config)
    request = _build_request(
        ctx=ctx,
        prompt=prompt,
        config=config,
        model=model,
        max_turns=max_turns,
        timeout_seconds=timeout_seconds,
    )

    t0 = time.perf_counter()
    outcome = await engine.run(request)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)

    extras.update(
        {
            "success": outcome.success,
            "elapsed_ms": elapsed_ms,
            "claude_input_tokens": outcome.input_tokens,
            "claude_output_tokens": outcome.output_tokens,
            "cost_usd": outcome.cost_usd,
        }
    )
    if outcome.error:
        extras["error"] = outcome.error[:1000]

    # Replace the placeholder kept_count with the live row count Claude
    # actually persisted via the MCP write handler. Logged for ops too.
    feature_count = await _count_synthesized_features(config)
    extras["kept_count"] = feature_count
    extras["features_synthesized"] = feature_count

    # Coverage audit — emit synthetic features for any cluster files
    # that didn't make it into one of Claude's features. Generic across
    # any codebase: requires path-segment evidence + minimum file count
    # before promoting (see ``coverage_audit.py``).
    audit_count = 0
    if outcome.success:
        audit_count = await _run_coverage_audit(config)
        extras["coverage_audit_features"] = audit_count

    logger.info(
        "scan_synthesize_done",
        repo=ctx.repo_name,
        success=outcome.success,
        elapsed_ms=elapsed_ms,
        cost_usd=outcome.cost_usd,
        features_synthesized=feature_count,
        coverage_audit_features=audit_count,
    )
    if not outcome.success:
        raise RuntimeError(f"synthesis failed: {outcome.error}")
    return StageOutput(communities=communities, dropped=[], extras=extras)


async def _run_coverage_audit(config: dict[str, Any]) -> int:
    """Invoke the post-synthesis coverage audit. Returns synthetic feature count.

    Resolves org/repo/scan/head_sha from the v2 stage context and calls
    ``audit_uncovered_clusters``. Cache-write style failure handling:
    any exception is swallowed and reported as 0 — the audit is a
    safety net, not a correctness gate.
    """
    v2 = resolve_v2_context(config)
    repo_id_raw = config.get("v2_repo_id")
    scan_id_raw = config.get("v2_scan_id")
    head_sha = str(config.get("ingest_head_sha") or "").strip()

    if v2 is None or repo_id_raw is None or scan_id_raw is None or not head_sha:
        return 0

    try:
        async with with_session(v2.org_id) as db:
            from app.repositories.organization import OrganizationRepository

            org = await OrganizationRepository(db).get_by_id(v2.org_id)
            if org is None:
                return 0
            written = await audit_uncovered_clusters(
                db,
                org=org,
                repo_id=uuid.UUID(str(repo_id_raw)),
                scan_id=uuid.UUID(str(scan_id_raw)),
                head_sha=head_sha,
            )
            await db.commit()
            return written
    except Exception:
        logger.exception("scan_synthesize_coverage_audit_failed")
        return 0


async def _count_synthesized_features(config: dict[str, Any]) -> int:
    """Count rows this scan wrote to ``synthesized_features`` for this repo.

    Returns 0 when the v2 context isn't threaded (manual sandbox runs)
    or the count query fails — the chip still reads sensibly because the
    rest of extras still describes what synthesis attempted.
    """
    org_id_str = config.get("v2_org_id")
    scan_id_str = config.get("v2_scan_id")
    repo_id_str = config.get("v2_repo_id")
    if not org_id_str or not scan_id_str or not repo_id_str:
        return 0

    from sqlalchemy import func, select

    from app.models.synthesized_feature import SynthesizedFeature
    from app.scan.session import with_session

    try:
        org_id = uuid.UUID(str(org_id_str))
        scan_id = uuid.UUID(str(scan_id_str))
        repo_id = uuid.UUID(str(repo_id_str))
    except ValueError:
        return 0

    try:
        async with with_session(org_id) as db:
            stmt = (
                select(func.count())
                .select_from(SynthesizedFeature)
                .where(
                    SynthesizedFeature.org_id == org_id,
                    SynthesizedFeature.scan_id == scan_id,
                    SynthesizedFeature.repo_id == repo_id,
                    SynthesizedFeature.superseded_at.is_(None),
                )
            )
            result = await db.execute(stmt)
            return int(result.scalar_one() or 0)
    except Exception:
        logger.exception("scan_synthesize_feature_count_failed")
        return 0


def _resolve_engine(config: dict[str, Any]) -> SynthesisEngine:
    """Pick the synthesis engine (Strategy pattern).

    Today we only ship ``ClaudeCodeEngine``. ``engine`` config knob is
    accepted but only ``"claude_code"`` is recognised; future
    ``"anthropic_sdk"`` will plug in here without touching callers.
    """
    name = str(config.get("engine", "claude_code"))
    if name == "claude_code":
        return ClaudeCodeEngine()
    raise ValueError(f"Unknown synthesis engine: {name!r}")


def _build_request(
    *,
    ctx: StageContext,
    prompt: str,
    config: dict[str, Any],
    model: str,
    max_turns: int,
    timeout_seconds: int,
) -> SynthesisRequest:
    """Assemble the engine request, raising if MCP details are missing."""
    mcp_backend_url = config.get("mcp_backend_url")
    mcp_token = config.get("mcp_token")
    if not mcp_backend_url or not mcp_token:
        raise RuntimeError(
            "synthesize stage requires mcp_backend_url + mcp_token in config "
            "(set them when launching a non-dry-run synthesis)"
        )
    return SynthesisRequest(
        prompt=prompt,
        working_dir=ctx.repo_path,
        repo_name=ctx.repo_name,
        mcp_backend_url=mcp_backend_url,
        mcp_token=mcp_token,
        model=model,
        max_turns=max_turns,
        timeout_seconds=timeout_seconds,
    )
