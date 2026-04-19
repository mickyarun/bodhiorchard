# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Thin async wrapper around the Slack Web API.

Consolidates all outbound Slack HTTP calls into a single module.
Uses httpx for async HTTP with explicit timeouts.
"""

import httpx
import structlog

logger = structlog.get_logger(__name__)

_SLACK_BASE = "https://slack.com/api"
_TIMEOUT = 10


async def conversations_replies(
    token: str,
    channel: str,
    ts: str,
    *,
    limit: int = 50,
) -> list[dict]:
    """Fetch threaded replies for a message.

    Args:
        token: Slack bot token (xoxb-...).
        channel: Channel ID.
        ts: Thread parent timestamp.
        limit: Max messages to return.

    Returns:
        List of message dicts (includes the parent message as first element).
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{_SLACK_BASE}/conversations.replies",
            params={"channel": channel, "ts": ts, "limit": limit},
            headers={"Authorization": f"Bearer {token}"},
            timeout=_TIMEOUT,
        )
        data = resp.json()
        if not data.get("ok"):
            logger.warning("slack_conversations_replies_failed", error=data.get("error"))
            return []
        return data.get("messages", [])


async def conversations_history(
    token: str,
    channel: str,
    *,
    latest: str | None = None,
    inclusive: bool = True,
    limit: int = 1,
) -> list[dict]:
    """Fetch channel messages (used to retrieve a single message by timestamp).

    Args:
        token: Slack bot token.
        channel: Channel ID.
        latest: Timestamp of the latest message to include.
        inclusive: Whether to include the message at `latest`.
        limit: Number of messages to return.

    Returns:
        List of message dicts.
    """
    params: dict[str, str | int] = {"channel": channel, "limit": limit}
    if latest:
        params["latest"] = latest
        params["inclusive"] = str(inclusive).lower()

    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{_SLACK_BASE}/conversations.history",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
            timeout=_TIMEOUT,
        )
        data = resp.json()
        if not data.get("ok"):
            logger.warning("slack_conversations_history_failed", error=data.get("error"))
            return []
        return data.get("messages", [])


async def chat_post_message(
    token: str,
    channel: str,
    text: str,
    *,
    thread_ts: str | None = None,
) -> dict | None:
    """Post a message to a Slack channel or thread.

    Args:
        token: Slack bot token.
        channel: Channel ID.
        text: Message text (supports mrkdwn).
        thread_ts: If provided, posts as a threaded reply.

    Returns:
        The full Slack API response dict, or None on failure.
    """
    payload: dict[str, str] = {"channel": channel, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_SLACK_BASE}/chat.postMessage",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
            timeout=_TIMEOUT,
        )
        data = resp.json()
        if not data.get("ok"):
            logger.warning("slack_chat_post_message_failed", error=data.get("error"))
            return None
        return data


async def reactions_add(
    token: str,
    channel: str,
    ts: str,
    name: str,
) -> bool:
    """Add an emoji reaction to a message.

    Args:
        token: Slack bot token.
        channel: Channel ID.
        ts: Message timestamp to react to.
        name: Emoji name without colons (e.g. "eyes").

    Returns:
        True if the reaction was added successfully.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_SLACK_BASE}/reactions.add",
            json={"channel": channel, "timestamp": ts, "name": name},
            headers={"Authorization": f"Bearer {token}"},
            timeout=_TIMEOUT,
        )
        data = resp.json()
        if not data.get("ok") and data.get("error") != "already_reacted":
            logger.warning("slack_reactions_add_failed", error=data.get("error"))
            return False
        return True


async def users_list(token: str) -> list[dict]:
    """Fetch all members of the Slack workspace.

    Args:
        token: Slack bot token.

    Returns:
        List of user dicts from the Slack API.
    """
    members: list[dict] = []
    cursor = ""
    async with httpx.AsyncClient() as client:
        while True:
            params: dict[str, str | int] = {"limit": 200}
            if cursor:
                params["cursor"] = cursor
            resp = await client.get(
                f"{_SLACK_BASE}/users.list",
                params=params,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30,
            )
            data = resp.json()
            if not data.get("ok"):
                logger.warning("slack_users_list_failed", error=data.get("error"))
                return members
            members.extend(data.get("members", []))
            cursor = data.get("response_metadata", {}).get("next_cursor", "")
            if not cursor:
                break
    return members


async def users_info(token: str, user_id: str) -> dict | None:
    """Fetch a Slack user's profile by their user ID.

    Args:
        token: Slack bot token.
        user_id: Slack user ID (e.g. U03BNGNFR8V).

    Returns:
        The user dict from the Slack API, or None on failure.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{_SLACK_BASE}/users.info",
            params={"user": user_id},
            headers={"Authorization": f"Bearer {token}"},
            timeout=_TIMEOUT,
        )
        data = resp.json()
        if not data.get("ok"):
            logger.warning("slack_users_info_failed", error=data.get("error"), user_id=user_id)
            return None
        return data.get("user")


async def users_get_presence(token: str, user_id: str) -> str | None:
    """Fetch a Slack user's presence ('active' or 'away').

    Uses Slack Web API users.getPresence. Requires users:read scope.

    Args:
        token: Slack bot token.
        user_id: Slack user ID.

    Returns:
        'active' or 'away', or None on failure.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{_SLACK_BASE}/users.getPresence",
            params={"user": user_id},
            headers={"Authorization": f"Bearer {token}"},
            timeout=_TIMEOUT,
        )
        data = resp.json()
        if not data.get("ok"):
            error_code = data.get("error", "unknown")
            is_auth_err = error_code == "invalid_auth"
            logger.warning(
                "slack_users_get_presence_failed",
                error=error_code,
                user_id=user_id,
                token_prefix=token[:10] + "..." if len(token) > 10 else "***",
                hint="check ENCRYPTION_KEY and stored token" if is_auth_err else None,
            )
            return None
        return data.get("presence")


async def conversations_open(token: str, user_id: str) -> str | None:
    """Open (or resume) a direct-message conversation with a Slack user.

    Args:
        token: Slack bot token.
        user_id: Slack user ID to DM.

    Returns:
        The DM channel ID, or None on failure.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_SLACK_BASE}/conversations.open",
                json={"users": user_id},
                headers={"Authorization": f"Bearer {token}"},
                timeout=_TIMEOUT,
            )
            data = resp.json()
            if not data.get("ok"):
                logger.warning(
                    "slack_conversations_open_failed",
                    error=data.get("error"),
                    user_id=user_id,
                )
                return None
            channel_id = data.get("channel", {}).get("id")
            if not channel_id:
                logger.warning(
                    "slack_conversations_open_no_channel_id",
                    user_id=user_id,
                )
            return channel_id
    except (httpx.HTTPError, ValueError) as exc:
        logger.error(
            "slack_conversations_open_error",
            error=str(exc),
            user_id=user_id,
        )
        return None


async def auth_test(token: str) -> dict | None:
    """Call auth.test to retrieve bot/team info.

    Args:
        token: Slack bot token.

    Returns:
        Dict with team_id, bot_id, user_id, etc., or None on failure.
    """
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{_SLACK_BASE}/auth.test",
            headers={"Authorization": f"Bearer {token}"},
            timeout=_TIMEOUT,
        )
        data = resp.json()
        if not data.get("ok"):
            logger.warning("slack_auth_test_failed", error=data.get("error"))
            return None
        return data
