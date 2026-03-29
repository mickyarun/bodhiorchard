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
                    owner_repo=owner_repo,
                    pr_number=pr_number,
                )
                return None

