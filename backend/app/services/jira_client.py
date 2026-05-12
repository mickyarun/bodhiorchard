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

"""Async Jira Cloud REST API client.

Provides paginated issue search, project listing, and connection
testing against Jira Cloud v3 API. Includes rate limiting with
exponential backoff on 429 responses.

Usage::

    client = JiraClient(site_url="https://x.atlassian.net",
                        email="a@b.com", api_token="tok")
    projects = await client.list_projects()
    async for batch in client.search_issues("project = FOO"):
        for issue in batch:
            print(issue["key"])
"""

import asyncio
import base64
from collections.abc import AsyncIterator
from typing import Any, cast

import httpx
import structlog

logger = structlog.get_logger(__name__)

_PAGE_SIZE = 100
_MAX_RETRIES = 5
_REQUEST_TIMEOUT = 30.0


class JiraApiError(Exception):
    """Raised when a Jira API call fails after retries."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


class JiraClient:
    """Async Jira Cloud REST API client with rate limiting.

    Uses Basic Auth (email + API token) and targets Jira REST API v3.

    Args:
        site_url: Jira Cloud URL, e.g. ``https://team.atlassian.net``.
        email: Atlassian account email.
        api_token: Jira API token (not PAT).
    """

    def __init__(self, site_url: str, email: str, api_token: str) -> None:
        self._base_url = site_url.rstrip("/")
        creds = base64.b64encode(f"{email}:{api_token}".encode()).decode()
        self._headers = {
            "Authorization": f"Basic {creds}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        self._client = httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)

    async def close(self) -> None:
        """Close the underlying HTTP client and release connections."""
        await self._client.aclose()

    async def __aenter__(self) -> "JiraClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    # ── Connection & Metadata ─────────────────────────────────────

    async def test_connection(self) -> dict[str, Any]:
        """Test the connection and return server info.

        Returns:
            Dict with ``baseUrl``, ``serverTitle``, ``version``, etc.

        Raises:
            JiraApiError: On auth failure or unreachable server.
        """
        data = await self._get("/rest/api/3/serverInfo")
        if not isinstance(data, dict):
            raise JiraApiError(0, "Unexpected response shape for /serverInfo")
        return data

    async def get_site_identifier(self) -> str:
        """Return a stable site identifier for this Jira instance.

        Uses the ``baseUrl`` from ``/rest/api/3/serverInfo`` as a
        stable identifier. Note: this is NOT the Atlassian Cloud ID
        (UUID from ``/oauth/token/accessible-resources``). A true
        Cloud ID would require OAuth — for API-token auth we use
        the canonical base URL instead.

        Returns:
            The Jira site's canonical base URL (e.g. ``https://team.atlassian.net``).
        """
        info = await self.test_connection()
        return cast(str, info.get("baseUrl", self._base_url))

    async def list_projects(self) -> list[dict[str, Any]]:
        """List all accessible Jira projects.

        Returns:
            List of project dicts with ``key``, ``name``, ``lead``, etc.
        """
        data = await self._get("/rest/api/3/project/search", params={"maxResults": 100})
        if not isinstance(data, dict):
            return []
        return cast(list[dict[str, Any]], data.get("values", []))

    async def get_issue(self, issue_key: str) -> dict[str, Any]:
        """Fetch a single issue by key.

        Args:
            issue_key: e.g. ``"PROJ-123"``.

        Returns:
            Full issue dict with fields.
        """
        data = await self._get(f"/rest/api/3/issue/{issue_key}")
        if not isinstance(data, dict):
            raise JiraApiError(0, f"Unexpected response shape for issue {issue_key}")
        return data

    # ── Paginated Search ──────────────────────────────────────────

    async def count_issues(self, jql: str) -> int:
        """Return total count of issues matching a JQL query.

        The new ``/search/jql`` endpoint may not return ``total`` reliably.
        Falls back to fetching all issue keys (lightweight) and counting.
        """
        data = await self._get(
            "/rest/api/3/search/jql",
            params={"jql": jql, "maxResults": 100, "fields": "summary"},
        )
        if not isinstance(data, dict):
            return 0

        # Try total field first (still present on some Jira instances)
        total = data.get("total")
        if total is not None and total > 0:
            return cast(int, total)

        # Fall back to counting issues in the response
        issues = data.get("issues", [])
        count = len(issues)

        # If there's a next page, keep counting
        next_token = data.get("nextPageToken")
        while next_token:
            page = await self._get(
                "/rest/api/3/search/jql",
                params={
                    "jql": jql,
                    "maxResults": 100,
                    "fields": "summary",
                    "nextPageToken": next_token,
                },
            )
            if not isinstance(page, dict):
                break
            page_issues = page.get("issues", [])
            count += len(page_issues)
            next_token = page.get("nextPageToken")
            if not page_issues:
                break

        return count

    async def search_issues(
        self,
        jql: str,
        fields: list[str] | None = None,
        *,
        start_at: int = 0,
    ) -> AsyncIterator[list[dict[str, Any]]]:
        """Paginated JQL search yielding batches of issues.

        Uses ``GET /rest/api/3/search/jql`` with ``nextPageToken``
        cursor pagination (required since Atlassian removed the old
        ``/rest/api/3/search`` POST endpoint in 2026).

        Args:
            jql: JQL query string.
            fields: List of field names to include. Defaults to common set.
            start_at: Starting offset (for resume — skip first N issues).

        Yields:
            Lists of issue dicts (up to ``_PAGE_SIZE`` per batch).
        """
        if fields is None:
            fields = _DEFAULT_FIELDS

        fields_str = ",".join(fields)
        next_page_token: str | None = None
        fetched = 0

        while True:
            params: dict[str, Any] = {
                "jql": jql,
                "maxResults": _PAGE_SIZE,
                "fields": fields_str,
            }
            if next_page_token:
                params["nextPageToken"] = next_page_token

            data = await self._get("/rest/api/3/search/jql", params=params)
            if not isinstance(data, dict):
                break

            issues = data.get("issues", [])

            if not issues:
                break

            # Handle start_at offset by skipping early results
            if fetched + len(issues) <= start_at:
                fetched += len(issues)
            elif fetched < start_at:
                skip = start_at - fetched
                yield issues[skip:]
                fetched += len(issues)
            else:
                yield issues
                fetched += len(issues)

            # Check for next page
            next_page_token = data.get("nextPageToken")
            if not next_page_token:
                break

            # Rate limiting: pause between pages
            await asyncio.sleep(1.0)

    async def get_project_statuses(self, project_key: str) -> list[dict[str, Any]]:
        """Get all statuses available in a project.

        Returns:
            List of status dicts with ``name``, ``statusCategory``, etc.
        """
        data = await self._get(f"/rest/api/3/project/{project_key}/statuses")
        if not isinstance(data, list):
            return []
        # Flatten: each issue type has its own status list
        seen: set[str] = set()
        statuses: list[dict[str, Any]] = []
        for issue_type_entry in data:
            for status in issue_type_entry.get("statuses", []):
                name = status.get("name", "")
                if name not in seen:
                    seen.add(name)
                    statuses.append(status)
        return statuses

    # ── HTTP internals ────────────────────────────────────────────

    async def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """GET request with retry and rate-limit handling."""
        return await self._request("GET", path, params=params)

    async def _post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST request with retry and rate-limit handling."""
        result = await self._request("POST", path, json=json)
        if isinstance(result, list):
            return {"values": result}
        return result

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        """Execute an HTTP request with retries and backoff.

        Uses ``self._client`` (created once in ``__init__``) so the
        TCP connection pool is reused across all requests during the
        client's lifetime.

        Retries on:
        - 429 (rate limited): uses ``Retry-After`` header
        - 5xx (server errors): exponential backoff
        """
        url = f"{self._base_url}{path}"

        for attempt in range(_MAX_RETRIES):
            try:
                resp = await self._client.request(
                    method,
                    url,
                    headers=self._headers,
                    params=params,
                    json=json,
                )
            except httpx.RequestError as exc:
                if attempt < _MAX_RETRIES - 1:
                    delay = 2**attempt
                    logger.warning(
                        "jira_request_error_retry",
                        error=str(exc),
                        attempt=attempt,
                        delay=delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise JiraApiError(0, f"Connection failed: {exc}") from exc

            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "10"))
                logger.warning(
                    "jira_rate_limited",
                    retry_after=retry_after,
                    attempt=attempt,
                )
                await asyncio.sleep(retry_after)
                continue

            if resp.status_code >= 500 and attempt < _MAX_RETRIES - 1:
                delay = 2**attempt
                logger.warning(
                    "jira_server_error_retry",
                    status=resp.status_code,
                    attempt=attempt,
                    delay=delay,
                )
                await asyncio.sleep(delay)
                continue

            if resp.status_code >= 400:
                raise JiraApiError(
                    resp.status_code,
                    f"Jira API {method} {path} returned {resp.status_code}: {resp.text[:300]}",
                )

            return cast(dict[str, Any] | list[dict[str, Any]], resp.json())

        raise JiraApiError(0, f"Max retries ({_MAX_RETRIES}) exceeded for {method} {path}")


# ── Default fields for search ─────────────────────────────────────

_DEFAULT_FIELDS = [
    "summary",
    "description",
    "issuetype",
    "status",
    "priority",
    "assignee",
    "reporter",
    "labels",
    "components",
    "fixVersions",
    "parent",
    "subtasks",
    "comment",
    "attachment",
    "created",
    "updated",
]
