# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""Recovery paths for ``GitHubClient.create_pr_review`` on HTTP 422.

GitHub returns 422 ``"Path could not be resolved"`` when one or more
inline comments reference a file the PR diff doesn't touch. The handler
must keep the valid annotations instead of dropping ALL of them, and
only fall back to a body-only review when no inline comments survive.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.services.github_client import GitHubClient


def _err_422() -> httpx.HTTPStatusError:
    req = httpx.Request("POST", "https://api.github.com/x")
    resp = httpx.Response(422, request=req, text='{"message":"Unprocessable Entity"}')
    return httpx.HTTPStatusError("422", request=req, response=resp)


def _ok_response(body: dict[str, Any]) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=body)
    return resp


def _err_response() -> MagicMock:
    resp = MagicMock()
    resp.status_code = 422
    resp.text = '{"message":"Unprocessable Entity"}'
    resp.raise_for_status = MagicMock(side_effect=_err_422())
    return resp


def _comments() -> list[dict[str, Any]]:
    return [
        {"path": "src/a.py", "line": 1, "body": "good"},
        {"path": "src/b.py", "line": 2, "body": "good"},
        {"path": "src/PHANTOM.py", "line": 5, "body": "bad path"},
    ]


def _patch_async_client(responses: list[MagicMock]) -> Any:
    """Patch ``AsyncClient`` so each ``.post(...)`` returns the next response."""
    client_instance = MagicMock()
    client_instance.post = AsyncMock(side_effect=responses)
    client_instance.__aenter__ = AsyncMock(return_value=client_instance)
    client_instance.__aexit__ = AsyncMock(return_value=None)
    return patch(
        "app.services.github_client.AsyncClient",
        return_value=client_instance,
    )


async def test_happy_path_returns_response_unchanged() -> None:
    ok = _ok_response({"id": 99})
    captured: list[dict[str, Any]] = []

    async def fake_post(url: str, **kw: Any) -> MagicMock:
        captured.append(kw.get("json", {}))
        return ok

    client_instance = MagicMock()
    client_instance.post = AsyncMock(side_effect=fake_post)
    client_instance.__aenter__ = AsyncMock(return_value=client_instance)
    client_instance.__aexit__ = AsyncMock(return_value=None)

    with patch("app.services.github_client.AsyncClient", return_value=client_instance):
        client = GitHubClient("pat")
        result = await client.create_pr_review("o/r", 1, "summary", comments=_comments())

    assert result == {"id": 99}
    # Pin the GitHub Reviews API payload contract — refactors must not
    # drop ``event`` (request gets 422) or ``body`` (review is empty).
    sent = captured[0]
    assert sent["body"] == "summary"
    assert sent["event"] == "COMMENT"
    assert sent["comments"] == _comments()


async def test_422_filters_bad_path_and_retries_with_surviving_comments() -> None:
    # First POST 422s. Filter retry: list_pr_files returns only the two
    # valid paths. Second POST 200s with kept=[a.py, b.py].
    err = _err_response()
    ok = _ok_response({"id": 200})

    captured: list[dict[str, Any]] = []

    async def fake_post(url: str, **kw: Any) -> MagicMock:
        payload = kw.get("json", {})
        captured.append(payload)
        # First call returns the 422 (with comments); second returns 200.
        return err if len(captured) == 1 else ok

    client_instance = MagicMock()
    client_instance.post = AsyncMock(side_effect=fake_post)
    client_instance.__aenter__ = AsyncMock(return_value=client_instance)
    client_instance.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.services.github_client.AsyncClient", return_value=client_instance),
        patch.object(
            GitHubClient,
            "list_pr_files",
            new=AsyncMock(return_value=["src/a.py", "src/b.py"]),
        ),
    ):
        client = GitHubClient("pat")
        result = await client.create_pr_review("o/r", 1, "summary", comments=_comments())

    assert result == {"id": 200}
    assert len(captured) == 2  # original + filtered retry, no bodyless fallback
    retry_payload = captured[1]
    # Body keeps the original summary at the top, then appends a
    # ``<details>`` block listing the dropped comment so its content
    # still reaches the PR author.
    assert retry_payload["body"].startswith("summary")
    assert "<details>" in retry_payload["body"]
    assert "src/PHANTOM.py:5" in retry_payload["body"]
    assert "bad path" in retry_payload["body"]
    assert retry_payload["event"] == "COMMENT"
    kept_paths = {c["path"] for c in retry_payload["comments"]}
    assert kept_paths == {"src/a.py", "src/b.py"}


def test_format_dropped_comments_section_empty_returns_blank() -> None:
    assert GitHubClient._format_dropped_comments_section([]) == ""


def test_format_dropped_comments_section_renders_each_comment() -> None:
    out = GitHubClient._format_dropped_comments_section(
        [
            {"path": "src/x.py", "line": 7, "body": "first finding"},
            {"path": "src/y.py", "line": 42, "body": "second\nmultiline\nfinding"},
        ]
    )
    # Collapsible disclosure scaffold.
    assert "<details>" in out
    assert "</details>" in out
    assert "Additional review comments (2" in out
    # Per-comment location + body.
    assert "src/x.py:7" in out
    assert "src/y.py:42" in out
    assert "> first finding" in out
    # Multi-line body is line-quoted (no triple-backtick fence — agent
    # bodies often contain their own fences, nesting breaks renderer).
    assert "> second" in out
    assert "> multiline" in out
    assert "> finding" in out
    assert "```" not in out


def test_format_dropped_comments_section_handles_fenced_body() -> None:
    # A comment body that itself contains a fence must not break the
    # outer block — we use ``> `` line-quoting precisely to dodge this.
    out = GitHubClient._format_dropped_comments_section(
        [{"path": "src/z.py", "line": 1, "body": "before\n```py\ncode()\n```\nafter"}]
    )
    # Each line of the fenced body becomes a quoted line; the outer
    # block has no fence of its own.
    assert "> ```py" in out
    assert "> code()" in out
    assert "> ```" in out


async def test_422_with_all_bad_paths_falls_back_to_bodyless() -> None:
    # Every inline comment references a phantom file. After filtering,
    # ``kept`` is empty so we skip the filtered POST and go straight to
    # the body-only fallback, which lands the summary.
    err = _err_response()
    ok = _ok_response({"id": 300})

    captured: list[dict[str, Any]] = []

    async def fake_post(url: str, **kw: Any) -> MagicMock:
        captured.append(kw.get("json", {}))
        return err if len(captured) == 1 else ok

    client_instance = MagicMock()
    client_instance.post = AsyncMock(side_effect=fake_post)
    client_instance.__aenter__ = AsyncMock(return_value=client_instance)
    client_instance.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.services.github_client.AsyncClient", return_value=client_instance),
        patch.object(GitHubClient, "list_pr_files", new=AsyncMock(return_value=[])),
    ):
        client = GitHubClient("pat")
        result = await client.create_pr_review("o/r", 1, "summary", comments=_comments())

    assert result == {"id": 300}
    assert len(captured) == 2  # original (422) + bodyless (200), no middle retry
    assert "comments" not in captured[1]  # body-only payload
    # Bodyless fallback still surfaces ALL findings via the appended
    # details block — the agent's review never gets silently swallowed.
    bodyless = captured[1]["body"]
    assert bodyless.startswith("summary")
    assert "<details>" in bodyless
    for c in _comments():
        assert c["body"] in bodyless
        assert c["path"] in bodyless


async def test_422_filtered_retry_still_422_falls_back_to_bodyless() -> None:
    # Filter survives, retry still 422 (e.g. line number now stale).
    # Must still land the body-only summary.
    err1 = _err_response()
    err2 = _err_response()
    ok = _ok_response({"id": 400})

    captured: list[dict[str, Any]] = []

    async def fake_post(url: str, **kw: Any) -> MagicMock:
        captured.append(kw.get("json", {}))
        if len(captured) <= 2:
            return err1 if len(captured) == 1 else err2
        return ok

    client_instance = MagicMock()
    client_instance.post = AsyncMock(side_effect=fake_post)
    client_instance.__aenter__ = AsyncMock(return_value=client_instance)
    client_instance.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.services.github_client.AsyncClient", return_value=client_instance),
        patch.object(
            GitHubClient,
            "list_pr_files",
            new=AsyncMock(return_value=["src/a.py", "src/b.py"]),
        ),
    ):
        client = GitHubClient("pat")
        result = await client.create_pr_review("o/r", 1, "summary", comments=_comments())

    assert result == {"id": 400}
    assert len(captured) == 3  # original + filtered + bodyless
    assert "comments" not in captured[2]


async def test_non_422_returns_none_without_retry() -> None:
    # A 500 (or any non-422) is NOT recoverable — we want to surface the
    # failure to the caller (and to the timeline), not silently degrade.
    req = httpx.Request("POST", "https://api.github.com/x")
    resp = httpx.Response(500, request=req, text="server explode")
    err = httpx.HTTPStatusError("500", request=req, response=resp)

    err_resp = MagicMock()
    err_resp.status_code = 500
    err_resp.text = "server explode"
    err_resp.raise_for_status = MagicMock(side_effect=err)

    captured: list[dict[str, Any]] = []

    async def fake_post(url: str, **kw: Any) -> MagicMock:
        captured.append(kw.get("json", {}))
        return err_resp

    client_instance = MagicMock()
    client_instance.post = AsyncMock(side_effect=fake_post)
    client_instance.__aenter__ = AsyncMock(return_value=client_instance)
    client_instance.__aexit__ = AsyncMock(return_value=None)

    list_pr_files_mock = AsyncMock()
    with (
        patch("app.services.github_client.AsyncClient", return_value=client_instance),
        patch.object(GitHubClient, "list_pr_files", new=list_pr_files_mock),
    ):
        client = GitHubClient("pat")
        result = await client.create_pr_review("o/r", 1, "summary", comments=_comments())

    assert result is None
    assert len(captured) == 1  # no retry attempted
    list_pr_files_mock.assert_not_called()


async def test_filtered_retry_network_error_falls_through_to_bodyless() -> None:
    # Transport error (TCP reset, DNS) on the filtered retry must NOT
    # crash the caller — fall through to the bodyless attempt so the
    # summary still has a chance to land.
    err = _err_response()
    ok = _ok_response({"id": 500})

    captured: list[dict[str, Any]] = []
    calls = 0

    async def fake_post(url: str, **kw: Any) -> MagicMock:
        nonlocal calls
        captured.append(kw.get("json", {}))
        calls += 1
        if calls == 1:
            return err  # original 422
        if calls == 2:
            raise httpx.ConnectError("simulated TCP reset")
        return ok  # bodyless

    client_instance = MagicMock()
    client_instance.post = AsyncMock(side_effect=fake_post)
    client_instance.__aenter__ = AsyncMock(return_value=client_instance)
    client_instance.__aexit__ = AsyncMock(return_value=None)

    with (
        patch("app.services.github_client.AsyncClient", return_value=client_instance),
        patch.object(
            GitHubClient,
            "list_pr_files",
            new=AsyncMock(return_value=["src/a.py", "src/b.py"]),
        ),
    ):
        client = GitHubClient("pat")
        result = await client.create_pr_review("o/r", 1, "summary", comments=_comments())

    assert result == {"id": 500}
    assert calls == 3
    assert "comments" not in captured[2]


async def test_list_pr_files_empty_logs_distinct_diagnostic() -> None:
    # When ``list_pr_files`` returns ``[]`` AND we had inline comments,
    # the recovery path should log the distinct
    # ``github_review_list_files_empty_treating_as_bad`` so dashboards
    # can distinguish "agent invented all paths" from "GitHub /files
    # call hiccuped and returned nothing". structlog routes through its
    # own logger instance so caplog (stdlib) can't see it — patch the
    # module logger directly.
    err = _err_response()
    ok = _ok_response({"id": 600})

    captured: list[dict[str, Any]] = []
    calls = 0

    async def fake_post(url: str, **kw: Any) -> MagicMock:
        nonlocal calls
        captured.append(kw.get("json", {}))
        calls += 1
        return err if calls == 1 else ok

    client_instance = MagicMock()
    client_instance.post = AsyncMock(side_effect=fake_post)
    client_instance.__aenter__ = AsyncMock(return_value=client_instance)
    client_instance.__aexit__ = AsyncMock(return_value=None)

    warn_events: list[str] = []

    def capture_warning(event: str, **kw: object) -> None:
        warn_events.append(event)

    from app.services import github_client as gc_mod

    with (
        patch.object(gc_mod.logger, "warning", side_effect=capture_warning),
        patch("app.services.github_client.AsyncClient", return_value=client_instance),
        patch.object(GitHubClient, "list_pr_files", new=AsyncMock(return_value=[])),
    ):
        client = GitHubClient("pat")
        await client.create_pr_review("o/r", 1, "summary", comments=_comments())

    assert "github_review_list_files_empty_treating_as_bad" in warn_events


@pytest.mark.parametrize("inline", [None, []])
async def test_422_without_inline_returns_none(inline: list[dict[str, Any]] | None) -> None:
    # When there were no inline comments to begin with, a 422 isn't a
    # "drop the bad paths" situation — there's nothing to filter. Return
    # None so the caller can decide what to do.
    err = _err_response()
    with _patch_async_client([err]):
        client = GitHubClient("pat")
        result = await client.create_pr_review("o/r", 1, "summary", comments=inline)
    assert result is None
