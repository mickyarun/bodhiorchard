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

"""Redis-backed per-token rate limiter for the MCP tool endpoint.

Uses a sliding-window-ish fixed-bucket counter: one Redis key per
``(token-or-org-id, ip, minute-bucket)`` that increments by the per-tool
cost weight. The key expires after 65 seconds so memory pressure stays
bounded.

When Redis is unavailable, the limiter **fails open** (logs a warning and
allows the call). Audit-log entries still record the call, so abuse is
detectable post-hoc. Failing closed would create a single point of
failure where a Redis blip takes down all MCP traffic — unacceptable for
a customer-facing AI integration.
"""

import time

import structlog
from fastapi import HTTPException, Request, status
from redis.exceptions import RedisError

from app.mcp.auth import MCPAuthResult
from app.services.redis_client import get_redis

logger = structlog.get_logger(__name__)

# Per-tool cost weights. Expensive tools (embed + pgvector) cost more,
# cheap lookups cost less. Defaults to 1 for unknown tools.
TOOL_COSTS: dict[str, int] = {
    "get_features": 5,
    "get_bud_context": 1,
    "list_design_systems": 1,
    "get_design_system": 2,
    # Single indexed AgentSkill lookup — comparable to get_bud_context.
    "get_prompt": 1,
    "get_team_context": 1,
    "write_bud": 10,
    # Code-graph tools are pgvector-heavy; weight similarly to features.
    "code_impact": 5,
    "code_query": 3,
    "code_context": 3,
    "code_community": 3,
    "code_god_nodes": 3,
    "code_stats": 1,
}

# Bucket of 60 units per minute per (token, ip). A read-heavy desktop AI
# session lands around 5–15 units/minute; this comfortably accommodates
# legitimate use while throttling automated abuse.
BUCKET_UNITS_PER_MINUTE = 60
# Absolute ceiling across ALL IPs for a single token. Catches a leaked
# token being hammered from a botnet (many IPs, each under the per-IP cap).
TOKEN_GLOBAL_UNITS_PER_MINUTE = 300


def _bucket_minute() -> int:
    """Current minute since epoch — fixed-window bucket key."""
    return int(time.time() // 60)


def _cost(tool_name: str) -> int:
    return TOOL_COSTS.get(tool_name, 1)


def _principal_id(auth: MCPAuthResult) -> str:
    """Stable id for rate-limiting: prefer user, fall back to org."""
    if auth.user is not None:
        return f"user:{auth.user.id}"
    return f"org:{auth.org.id}"


def _client_ip(request: Request) -> str:
    """Best-effort client IP for keying the rate limit bucket."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def enforce_rate_limit(
    *,
    request: Request,
    auth: MCPAuthResult,
    tool_name: str,
) -> None:
    """Raise 429 if the (token, ip) bucket would overflow, else atomically
    increment.

    Two checks per call:
      1. Per-(token, ip) bucket (BUCKET_UNITS_PER_MINUTE).
      2. Global per-token bucket (TOKEN_GLOBAL_UNITS_PER_MINUTE) so a
         botnet-distributed attack can't stay under the per-IP cap.
    """
    cost = _cost(tool_name)
    principal = _principal_id(auth)
    ip = _client_ip(request)
    minute = _bucket_minute()

    redis = await get_redis()
    if redis is None:
        # Redis down — fail open. Audit log still captures the call. Log
        # principal/ip/org so we can reconstruct who was un-throttled if
        # Redis flaps during an incident.
        logger.warning(
            "mcp_rate_limit_redis_unavailable",
            tool=tool_name,
            principal=principal,
            ip=ip,
            org_id=str(auth.org.id),
        )
        return

    per_ip_key = f"mcp_rate:{principal}:{ip}:{minute}"
    global_key = f"mcp_rate:{principal}:_global:{minute}"

    # INCRBY returns the new value. EXPIRE only sets a TTL if one isn't
    # already set (NX) — keeps the bucket aligned with the minute window
    # without resetting the TTL on every call. Catch RedisError narrowly
    # so a mid-call outage matches the get_redis()-returned-None policy
    # (fail open + observable warning) rather than 500-ing the caller.
    try:
        per_ip_total = await redis.incrby(per_ip_key, cost)
        if per_ip_total == cost:
            await redis.expire(per_ip_key, 65)
        global_total = await redis.incrby(global_key, cost)
        if global_total == cost:
            await redis.expire(global_key, 65)
    except RedisError:
        logger.warning(
            "mcp_rate_limit_redis_error_fail_open",
            tool=tool_name,
            principal=principal,
            ip=ip,
            org_id=str(auth.org.id),
            exc_info=True,
        )
        return

    if per_ip_total > BUCKET_UNITS_PER_MINUTE:
        logger.info(
            "mcp_rate_limited_per_ip",
            principal=principal,
            ip=ip,
            tool=tool_name,
            total=per_ip_total,
            cap=BUCKET_UNITS_PER_MINUTE,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded for this client. Retry shortly.",
            headers={"Retry-After": "60"},
        )

    if global_total > TOKEN_GLOBAL_UNITS_PER_MINUTE:
        logger.warning(
            "mcp_rate_limited_global",
            principal=principal,
            tool=tool_name,
            total=global_total,
            cap=TOKEN_GLOBAL_UNITS_PER_MINUTE,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded for this token. Retry shortly.",
            headers={"Retry-After": "60"},
        )
