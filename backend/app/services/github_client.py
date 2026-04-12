"""Async GitHub API client for PR operations.

Thin wrapper around httpx for GitHub REST API v3.
Handles auth headers and response parsing.
"""

import structlog
from httpx import AsyncClient, HTTPStatusError

logger = structlog.get_logger(__name__)

_BASE_URL = "https://api.github.com"
_API_VERSION = "2022-11-28"


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
        comments: list[dict] | None = None,
    ) -> dict | None:
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
        payload: dict = {"body": body, "event": "COMMENT"}
        if comments:
            payload["comments"] = comments

        async with AsyncClient(timeout=30) as client:
            try:
                resp = await client.post(url, json=payload, headers=self._headers)
                resp.raise_for_status()
                return resp.json()
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
                        return fallback.json()
                    except HTTPStatusError:
                        pass
                return None

    async def get_review_comments(
        self,
        owner_repo: str,
        pr_number: int,
        review_id: int,
    ) -> list[dict]:
        """Fetch inline comments for a specific PR review.

        Returns list of comment dicts with path, line, body, etc.
        """
        url = f"{_BASE_URL}/repos/{owner_repo}/pulls/{pr_number}/reviews/{review_id}/comments"
        async with AsyncClient(timeout=30) as client:
            try:
                resp = await client.get(url, headers=self._headers)
                resp.raise_for_status()
                return resp.json()
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
    ) -> list[dict]:
        """Fetch the list of commits in a pull request.

        Used by release-stage detection to walk the commits of a release PR
        (e.g. develop \u2192 release/uat) and find which BUDs are included.
        Each entry has at least ``sha`` and ``commit.message``; we paginate
        through all pages because release PRs commonly carry hundreds of
        commits across multiple BUDs.
        """
        url = f"{_BASE_URL}/repos/{owner_repo}/pulls/{pr_number}/commits"
        all_commits: list[dict] = []
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
