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

"""Async GitHub API client for PR operations.

Thin wrapper around httpx for GitHub REST API v3.
Handles auth headers and response parsing.
"""

import json
import os
from pathlib import Path
from typing import Any, cast

import structlog
from httpx import AsyncClient, HTTPStatusError

logger = structlog.get_logger(__name__)

_BASE_URL = "https://api.github.com"
_API_VERSION = "2022-11-28"

# Testing affordance: when this env var is set to a JSON file path, the
# ``list_pr_files`` helper short-circuits the GitHub network call and
# returns the file list for ``<owner_repo>:<pr_number>`` from that file.
# Used by the local smoke-harness for the PR-merge narrow-synthesis flow
# so synthetic webhooks can drive realistic ``changed_files`` without
# needing a real GitHub PR. Unset in production; absence is a noop.
_MOCK_PR_FILES_ENV = "BODHI_MOCK_PR_FILES_PATH"


def _read_mock_pr_files(owner_repo: str, pr_number: int) -> list[str] | None:
    """Look up mock PR files from the env-pointed JSON file.

    Returns the file list when both the env var is set AND the file
    contains a key matching ``<owner_repo>:<pr_number>``. Returns
    ``None`` in every other case so the caller falls through to the
    real GitHub API path — unrelated PRs in test runs are unaffected.
    """
    override = os.environ.get(_MOCK_PR_FILES_ENV)
    if not override:
        return None
    try:
        data = json.loads(Path(override).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "github_pr_files_mock_unreadable",
            path=override,
            error=str(exc),
        )
        return None
    key = f"{owner_repo}:{pr_number}"
    files = data.get(key)
    if not isinstance(files, list):
        return None
    return [p for p in files if isinstance(p, str)]


class GitHubClient:
    """Async GitHub API client using a PAT for authentication."""

    def __init__(self, pat: str) -> None:
        self._headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {pat}",
            "X-GitHub-Api-Version": _API_VERSION,
        }

    async def create_pr_review(
        self,
        owner_repo: str,
        pr_number: int,
        body: str,
        comments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Post a review with inline comments on a PR.

        Args:
            owner_repo: "owner/repo" string.
            pr_number: PR number.
            body: Review summary text.
            comments: List of inline comments with path, line, body.

        Returns:
            GitHub API response dict, or None on failure.
        """
        url = f"{_BASE_URL}/repos/{owner_repo}/pulls/{pr_number}/reviews"
        payload: dict[str, Any] = {"body": body, "event": "COMMENT"}
        if comments:
            payload["comments"] = comments

        async with AsyncClient(timeout=30) as client:
            try:
                resp = await client.post(url, json=payload, headers=self._headers)
                resp.raise_for_status()
                return cast(dict[str, Any], resp.json())
            except HTTPStatusError:
                logger.error(
                    "github_review_failed",
                    status=resp.status_code,
                    response_body=resp.text[:500],
                    owner_repo=owner_repo,
                    pr_number=pr_number,
                )
                # Retry without inline comments (422 often means stale line refs)
                if resp.status_code == 422 and comments:
                    logger.warning(
                        "github_review_422_retry_without_inline",
                        pr_number=pr_number,
                        inline_count=len(comments),
                    )
                    try:
                        fallback = await client.post(
                            url,
                            json={"body": body, "event": "COMMENT"},
                            headers=self._headers,
                        )
                        fallback.raise_for_status()
                        logger.info(
                            "github_review_fallback_posted",
                            pr_number=pr_number,
                        )
                        return cast(dict[str, Any], fallback.json())
                    except HTTPStatusError:
                        pass
                return None

    async def list_pull_requests(
        self,
        owner_repo: str,
        *,
        head: str | None = None,
        state: str = "open",
    ) -> list[dict[str, object]]:
        """List pull requests on a repository.

        Used by ``create_setup_pr`` to detect a pre-existing open PR for the
        ``bodhiorchard/init-setup`` head before opening a new one — keeps the
        flow idempotent against repos that already have a setup branch + PR
        from prior testing.

        Args:
            owner_repo: ``"owner/repo"`` string.
            head: Optional ``"owner:branch"`` filter. GitHub only honours the
                full ``owner:branch`` shape, not a bare branch name.
            state: ``open``, ``closed``, or ``all``.

        Returns:
            List of PR dicts (each with at least ``number``, ``html_url``,
            ``state``). Empty list on HTTP error.
        """
        url = f"{_BASE_URL}/repos/{owner_repo}/pulls"
        params: dict[str, str] = {"state": state, "per_page": "100"}
        if head:
            params["head"] = head
        async with AsyncClient(timeout=30) as client:
            try:
                resp = await client.get(url, headers=self._headers, params=params)
                resp.raise_for_status()
            except HTTPStatusError:
                logger.error(
                    "github_list_prs_failed",
                    status=resp.status_code,
                    owner_repo=owner_repo,
                    head=head,
                )
                return []
            payload = resp.json()
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    async def create_pull_request(
        self,
        owner_repo: str,
        *,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> dict[str, object] | None:
        """Open a pull request via the GitHub REST API.

        On ``422 "A pull request already exists"`` GitHub returns the
        conflicting PR's URL inside ``errors[0].message``; rather than
        re-derive it we let the caller fall back to ``list_pull_requests``
        and adopt whatever's already there.

        Returns:
            Response dict (``number``, ``html_url``, ``state``, ...) on
            success, or ``None`` on any error.
        """
        url = f"{_BASE_URL}/repos/{owner_repo}/pulls"
        body_payload = {"title": title, "body": body, "head": head, "base": base}
        async with AsyncClient(timeout=30) as client:
            try:
                resp = await client.post(url, json=body_payload, headers=self._headers)
                resp.raise_for_status()
            except HTTPStatusError:
                logger.warning(
                    "github_create_pr_failed",
                    status=resp.status_code,
                    response_body=resp.text[:500],
                    owner_repo=owner_repo,
                    head=head,
                    base=base,
                )
                return None
            data = resp.json()
        if not isinstance(data, dict):
            return None
        return data

    async def get_review_comments(
        self,
        owner_repo: str,
        pr_number: int,
        review_id: int,
    ) -> list[dict[str, Any]]:
        """Fetch inline comments for a specific PR review.

        Returns list of comment dicts with path, line, body, etc.
        """
        url = f"{_BASE_URL}/repos/{owner_repo}/pulls/{pr_number}/reviews/{review_id}/comments"
        async with AsyncClient(timeout=30) as client:
            try:
                resp = await client.get(url, headers=self._headers)
                resp.raise_for_status()
                return cast(list[dict[str, Any]], resp.json())
            except HTTPStatusError:
                logger.error(
                    "github_get_review_comments_failed",
                    status=resp.status_code,
                    owner_repo=owner_repo,
                    review_id=review_id,
                )
                return []

    async def get_pr_commits(
        self,
        owner_repo: str,
        pr_number: int,
    ) -> list[dict[str, Any]]:
        """Fetch the list of commits in a pull request.

        Used by release-stage detection to walk the commits of a release PR
        (e.g. develop \u2192 release/uat) and find which BUDs are included.
        Each entry has at least ``sha`` and ``commit.message``; we paginate
        through all pages because release PRs commonly carry hundreds of
        commits across multiple BUDs.
        """
        url = f"{_BASE_URL}/repos/{owner_repo}/pulls/{pr_number}/commits"
        all_commits: list[dict[str, Any]] = []
        # GitHub paginates at 100/page; release PRs frequently exceed one
        # page. Cap at 30 pages (3000 commits) as a sanity ceiling — we'd
        # rather log and stop than hang on a runaway repo.
        page = 1
        async with AsyncClient(timeout=30) as client:
            while page <= 30:
                try:
                    resp = await client.get(
                        url,
                        headers=self._headers,
                        params={"per_page": 100, "page": page},
                    )
                    resp.raise_for_status()
                except HTTPStatusError:
                    logger.error(
                        "github_get_pr_commits_failed",
                        status=resp.status_code,
                        owner_repo=owner_repo,
                        pr_number=pr_number,
                        page=page,
                    )
                    return all_commits
                except Exception:
                    logger.error(
                        "github_get_pr_commits_connection_error",
                        owner_repo=owner_repo,
                        pr_number=pr_number,
                        page=page,
                        exc_info=True,
                    )
                    return all_commits
                batch = resp.json()
                if not batch:
                    break
                all_commits.extend(batch)
                if len(batch) < 100:
                    break
                page += 1
            else:
                logger.warning(
                    "github_get_pr_commits_pagination_cap_hit",
                    owner_repo=owner_repo,
                    pr_number=pr_number,
                    fetched=len(all_commits),
                )
        return all_commits

    async def list_pr_files(
        self,
        owner_repo: str,
        pr_number: int,
    ) -> list[str]:
        """Return the changed file paths for a pull request.

        Used by the PR-merge feature-reconcile job to intersect the PR's
        touched files against cached cluster file sets so untouched
        clusters can be skipped before any LLM cost is incurred. Paginates
        at 100 per page; caps at 30 pages (3000 files) — the same sanity
        ceiling :meth:`get_pr_commits` uses.

        Testing affordance: when ``BODHI_MOCK_PR_FILES_PATH`` is set and
        contains an entry for this ``owner_repo:pr_number`` key, the
        network call is skipped and the mock list returned. See
        :func:`_read_mock_pr_files`.
        """
        mock = _read_mock_pr_files(owner_repo, pr_number)
        if mock is not None:
            # WARNING level so a stale env var leaking into a non-dev
            # environment is loud in logs. Fall-through behaviour means
            # absence of the var (or a non-matching key) is silent.
            logger.warning(
                "github_list_pr_files_mocked",
                owner_repo=owner_repo,
                pr_number=pr_number,
                file_count=len(mock),
            )
            return mock
        url = f"{_BASE_URL}/repos/{owner_repo}/pulls/{pr_number}/files"
        out: list[str] = []
        page = 1
        async with AsyncClient(timeout=30) as client:
            while page <= 30:
                try:
                    resp = await client.get(
                        url,
                        headers=self._headers,
                        params={"per_page": 100, "page": page},
                    )
                    resp.raise_for_status()
                except HTTPStatusError:
                    logger.error(
                        "github_list_pr_files_failed",
                        status=resp.status_code,
                        owner_repo=owner_repo,
                        pr_number=pr_number,
                        page=page,
                    )
                    return out
                except Exception:
                    logger.error(
                        "github_list_pr_files_connection_error",
                        owner_repo=owner_repo,
                        pr_number=pr_number,
                        page=page,
                        exc_info=True,
                    )
                    return out
                batch = resp.json()
                if not batch:
                    break
                out.extend(item["filename"] for item in batch if "filename" in item)
                if len(batch) < 100:
                    break
                page += 1
            else:
                logger.warning(
                    "github_list_pr_files_pagination_cap_hit",
                    owner_repo=owner_repo,
                    pr_number=pr_number,
                    fetched=len(out),
                )
        return out
