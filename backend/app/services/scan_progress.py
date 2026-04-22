# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Scan progress tracking backed by Redis with in-memory fallback.

Provides a single source of truth for scan status that:
  * Survives server restarts (Redis)
  * Falls back gracefully when Redis is unavailable (in-memory dict)
  * Enforces **monotonically increasing** progress (never goes backwards)
  * Publishes every update to the event bus for WebSocket delivery
  * Auto-detects stuck scans after ``_STALE_TIMEOUT`` seconds of inactivity

Redis key layout:
  ``scan:{scan_id}``      — hash with all ScanStatus fields (TTL 2 h)
  ``scan_active:{org_id}`` — string pointing to the active scan_id (TTL 2 h)
"""

import json
import time

import structlog
from redis.asyncio import Redis

from app.schemas.skills import ScanStatus
from app.services.event_bus import publish

logger = structlog.get_logger(__name__)

_SCAN_TTL = 7200  # 2 hours
_STALE_TIMEOUT = 600  # 10 minutes — scan is considered stuck after this

# ── In-memory fallback ──────────────────────────────────────────────
_fallback: dict[str, dict] = {}
_org_scan_map: dict[str, str] = {}  # org_id → scan_id

# Fields stored in Redis / fallback dicts (must stay in sync with ScanStatus)
_HASH_FIELDS = (
    "scan_id",
    "org_id",
    "status",
    "scan_mode",
    "progress_pct",
    "features_indexed",
    "features_skipped",
    "profiles_found",
    "stale_cleaned",
    "unmatched_authors",
    "synthesis_warning",
    "setup_pr_message",
    "repo_warnings",
    "error",
    "updated_at",  # epoch timestamp for stale detection
)


def _decode_json_list(raw: object) -> list:
    """Parse a field stored as a JSON string back into a list."""
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw) if raw else []
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    if isinstance(raw, list):
        return raw
    return []


def _dict_to_scan_status(data: dict) -> ScanStatus:
    """Convert a stored dict to a ``ScanStatus`` model."""
    return ScanStatus(
        scan_id=data.get("scan_id", ""),
        status=data.get("status", "started"),
        scan_mode=data.get("scan_mode", "full"),
        progress_pct=int(data.get("progress_pct", 0)),
        features_indexed=int(data.get("features_indexed", 0)),
        features_skipped=int(data.get("features_skipped", 0)),
        profiles_found=int(data.get("profiles_found", 0)),
        stale_cleaned=int(data.get("stale_cleaned", 0)),
        unmatched_authors=_decode_json_list(data.get("unmatched_authors", "[]")),
        synthesis_warning=data.get("synthesis_warning"),
        setup_pr_message=data.get("setup_pr_message"),
        repo_warnings=_decode_json_list(data.get("repo_warnings", "[]")),
        error=data.get("error"),
    )


def _publish(scan_id: str, status: ScanStatus) -> None:
    """Publish scan status to the event bus for WebSocket delivery."""
    publish(f"scan:{scan_id}", status.model_dump(by_alias=True))


# ── Public API ──────────────────────────────────────────────────────


async def create_scan_progress(scan_id: str, org_id: str) -> ScanStatus:
    """Initialise a new scan progress entry.

    Args:
        scan_id: Unique scan identifier (UUID string).
        org_id: Organisation UUID string.

    Returns:
        The initial ``ScanStatus`` with ``status='started'`` and ``progress_pct=0``.
    """
    from app.services.redis_client import get_redis

    initial: dict = {
        "scan_id": scan_id,
        "org_id": org_id,
        "status": "started",
        "scan_mode": "full",
        "progress_pct": "0",
        "features_indexed": "0",
        "features_skipped": "0",
        "profiles_found": "0",
        "stale_cleaned": "0",
        "unmatched_authors": "[]",
        "synthesis_warning": "",
        "setup_pr_message": "",
        "repo_warnings": "[]",
        "error": "",
        "updated_at": str(time.time()),
    }

    redis = await get_redis()
    if redis is not None:
        key = f"scan:{scan_id}"
        await redis.hset(key, mapping=initial)
        await redis.expire(key, _SCAN_TTL)
        # Secondary index so checklist can find active scan for an org
        await redis.set(f"scan_active:{org_id}", scan_id, ex=_SCAN_TTL)
        logger.debug("scan_progress_created_redis", scan_id=scan_id)
    else:
        _fallback[scan_id] = dict(initial)
        _org_scan_map[org_id] = scan_id
        logger.debug("scan_progress_created_fallback", scan_id=scan_id)

    status = _dict_to_scan_status(initial)
    _publish(scan_id, status)
    return status


async def update_scan_progress(
    scan_id: str,
    *,
    status: str | None = None,
    progress_pct: int | None = None,
    **kwargs: object,
) -> ScanStatus:
    """Update scan progress with monotonic progress enforcement.

    ``progress_pct`` is clamped to ``max(current, requested)`` so the
    percentage never goes backwards.

    After the write, publishes the updated status to the event bus.

    Args:
        scan_id: Scan identifier.
        status: New status string (optional).
        progress_pct: Requested progress percentage (optional, monotonic).
        **kwargs: Any other ``ScanStatus`` field to update
            (e.g. ``features_indexed=12``, ``error="..."``).

    Returns:
        The updated ``ScanStatus``.
    """
    from app.services.redis_client import get_redis

    redis = await get_redis()
    if redis is not None:
        return await _update_redis(redis, scan_id, status, progress_pct, kwargs)
    return _update_fallback(scan_id, status, progress_pct, kwargs)


async def _update_redis(
    redis: Redis,  # type: ignore[type-arg]
    scan_id: str,
    new_status: str | None,
    new_pct: int | None,
    extras: dict,
) -> ScanStatus:
    """Update in Redis with monotonic guard."""
    key = f"scan:{scan_id}"

    updates: dict = {}
    if new_status is not None:
        updates["status"] = new_status

    if new_pct is not None:
        current_raw = await redis.hget(key, "progress_pct")
        current_pct = int(current_raw or 0)
        updates["progress_pct"] = str(max(current_pct, new_pct))

    for field, value in extras.items():
        if field in _HASH_FIELDS:
            if isinstance(value, list):
                updates[field] = json.dumps(value)
            elif value is None:
                updates[field] = ""
            else:
                updates[field] = str(value)

    # Always stamp updated_at on every write
    updates["updated_at"] = str(time.time())

    if updates:
        await redis.hset(key, mapping=updates)

    raw = await redis.hgetall(key)
    result = _dict_to_scan_status(raw)
    _publish(scan_id, result)
    return result


def _update_fallback(
    scan_id: str,
    new_status: str | None,
    new_pct: int | None,
    extras: dict,
) -> ScanStatus:
    """Update in-memory fallback with monotonic guard."""
    data = _fallback.get(scan_id)
    if data is None:
        logger.warning("scan_progress_fallback_not_found", scan_id=scan_id)
        data = {"scan_id": scan_id, "status": "started", "progress_pct": "0"}
        _fallback[scan_id] = data

    if new_status is not None:
        data["status"] = new_status

    if new_pct is not None:
        current_pct = int(data.get("progress_pct", 0))
        data["progress_pct"] = str(max(current_pct, new_pct))

    for field, value in extras.items():
        if field in _HASH_FIELDS:
            if isinstance(value, list):
                data[field] = json.dumps(value)
            elif value is None:
                data[field] = ""
            else:
                data[field] = str(value)

    # Always stamp updated_at on every write
    data["updated_at"] = str(time.time())

    result = _dict_to_scan_status(data)
    _publish(scan_id, result)

    # Clean up terminal scans from fallback to prevent unbounded growth
    if new_status in ("completed", "failed"):
        _fallback.pop(scan_id, None)
        # Clean org→scan mapping for this scan
        org_id = data.get("org_id")
        if org_id and _org_scan_map.get(org_id) == scan_id:
            _org_scan_map.pop(org_id, None)

    return result


async def append_repo_warning(
    scan_id: str,
    *,
    repo: str,
    phase: str,
    summary: str,
    hint: str | None = None,
) -> ScanStatus | None:
    """Append a non-fatal per-repo warning to the scan's warning list.

    The list is stored JSON-encoded so it survives Redis's flat hash
    layout. We read-modify-write which is fine here since scan progress
    is single-writer per scan_id.
    """
    current = await get_scan_progress(scan_id)
    if current is None:
        logger.warning("append_repo_warning_missing_scan", scan_id=scan_id)
        return None
    entry = {"repo": repo, "phase": phase, "summary": summary, "hint": hint}
    warnings = [w.model_dump() for w in current.repo_warnings] + [entry]
    return await update_scan_progress(scan_id, repo_warnings=warnings)


async def get_scan_progress(scan_id: str) -> ScanStatus | None:
    """Read current progress for a scan.

    Args:
        scan_id: Scan identifier.

    Returns:
        ``ScanStatus`` or ``None`` if not found.
    """
    from app.services.redis_client import get_redis

    redis = await get_redis()
    if redis is not None:
        raw = await redis.hgetall(f"scan:{scan_id}")
        if raw:
            return _dict_to_scan_status(raw)
        return None

    data = _fallback.get(scan_id)
    if data is not None:
        return _dict_to_scan_status(data)
    return None


async def cancel_scan(scan_id: str) -> ScanStatus | None:
    """Force-fail a scan. Used by the cancel endpoint and stale detection.

    Args:
        scan_id: Scan identifier.

    Returns:
        Updated ``ScanStatus`` or ``None`` if not found.
    """
    return await update_scan_progress(
        scan_id,
        status="failed",
        error="Scan cancelled (timed out or user-cancelled).",
    )


def _is_stale(data: dict) -> bool:
    """Check if a scan has gone stale (no updates for ``_STALE_TIMEOUT`` seconds)."""
    updated_at = float(data.get("updated_at", 0))
    if updated_at == 0:
        return False  # No timestamp — legacy entry, don't auto-fail
    return (time.time() - updated_at) > _STALE_TIMEOUT


async def get_active_scan_for_org(org_id: str) -> ScanStatus | None:
    """Find the in-progress scan for an organisation.

    Used by the setup checklist endpoint to display live progress
    without knowing the specific ``scan_id``.

    Auto-detects stuck scans: if a scan hasn't updated in
    ``_STALE_TIMEOUT`` seconds (10 min), it is automatically marked
    as failed so the UI unblocks.

    Args:
        org_id: Organisation UUID string.

    Returns:
        ``ScanStatus`` of the active scan, or ``None`` if no scan is running.
    """
    from app.services.redis_client import get_redis

    redis = await get_redis()
    if redis is not None:
        scan_id = await redis.get(f"scan_active:{org_id}")
        if scan_id:
            raw = await redis.hgetall(f"scan:{scan_id}")
            if not raw:
                await redis.delete(f"scan_active:{org_id}")
                return None

            if raw.get("status") in ("completed", "failed"):
                await redis.delete(f"scan_active:{org_id}")
                return None

            # Auto-fail stale scans
            if _is_stale(raw):
                logger.warning(
                    "scan_auto_failed_stale",
                    scan_id=scan_id,
                    last_update=raw.get("updated_at"),
                )
                await cancel_scan(scan_id)
                await redis.delete(f"scan_active:{org_id}")
                return None

            return _dict_to_scan_status(raw)
        return None

    # Fallback: check in-memory map
    scan_id = _org_scan_map.get(org_id)
    if scan_id:
        data = _fallback.get(scan_id)
        if not data or data.get("status") in ("completed", "failed"):
            _org_scan_map.pop(org_id, None)
            return None

        # Auto-fail stale scans
        if _is_stale(data):
            logger.warning(
                "scan_auto_failed_stale",
                scan_id=scan_id,
                last_update=data.get("updated_at"),
            )
            _update_fallback(scan_id, "failed", None, {
                "error": "Scan cancelled (timed out — no progress for 10 minutes).",
            })
            _org_scan_map.pop(org_id, None)
            return None

        return _dict_to_scan_status(data)
    return None
