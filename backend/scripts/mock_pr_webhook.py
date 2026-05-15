#!/usr/bin/env python3
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

"""Synthetic GitHub PR-merge webhook driver for the smoke harness.

Drives the PR-merge narrow-synthesis flow end-to-end against a locally
running backend, without needing a real GitHub PR. Three moving parts:

1. Look up the target tracked repo + its org by ``repo_id`` (Postgres),
   decrypt the org's GitHub webhook secret with the project's
   ``decrypt_secret`` helper.
2. Build a minimal ``pull_request`` payload with ``action=closed`` and
   ``merged=true``, HMAC-SHA256-sign it with the decrypted secret, and
   POST to the local webhook endpoint with the right
   ``X-Hub-Signature-256`` and ``X-GitHub-Event: pull_request`` headers.
3. Write/update the JSON fixture that the
   ``BODHI_MOCK_PR_FILES_PATH`` env-gate on
   :func:`GitHubClient.list_pr_files` reads, keyed by
   ``"<owner_repo>:<pr_number>"``, so the dispatcher's "what files did
   this PR touch?" query returns the simulated set instead of hitting
   the real GitHub API.

Usage::

    cd backend && python scripts/mock_pr_webhook.py \\
        --repo-id <uuid> \\
        --pr-number 7 \\
        --base-sha basesha \\
        --head-sha headsha \\
        --changed-files src/foo.py,src/bar.py

The script writes the changed-files JSON to
``$BODHI_MOCK_PR_FILES_PATH`` (default
``/tmp/bodhi-mock-pr-files.json``) and prints the export line the
backend must have in its environment before processing the webhook.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import hmac
import json
import os
import secrets
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

# The script lives under backend/scripts; make ``app`` importable when
# invoked as ``python scripts/mock_pr_webhook.py`` from ``backend/``.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.encryption import decrypt_secret  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.models.organization import Organization  # noqa: E402
from app.models.tracked_repository import TrackedRepository  # noqa: E402

DEFAULT_WEBHOOK_URL = "http://localhost:8000/api/v1/webhooks/github"
DEFAULT_MOCK_FILES_PATH = "/tmp/bodhi-mock-pr-files.json"  # noqa: S108 — dev tooling

# Hard-coded prod-safety: refuse to POST anywhere other than a loopback
# host unless the user passes ``--allow-non-localhost``. Stops an
# accidental ``--webhook-url https://prod.example.com/...`` from
# decrypting and using a real org's webhook secret against production.
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


def _parse_args() -> argparse.Namespace:
    """Parse CLI args for the synthetic webhook driver."""
    parser = argparse.ArgumentParser(
        prog="mock_pr_webhook",
        description="Post a signed synthetic pull_request merge webhook to a local backend.",
    )
    parser.add_argument("--repo-id", required=True, help="UUID of the tracked repo to target.")
    parser.add_argument("--pr-number", required=True, type=int, help="Synthetic PR number.")
    parser.add_argument("--base-sha", required=True, help="Pre-merge SHA.")
    parser.add_argument("--head-sha", required=True, help="Post-merge SHA (= merge_commit_sha).")
    parser.add_argument(
        "--changed-files",
        default="",
        help="Comma-separated list of repo-relative paths the PR 'touched'.",
    )
    parser.add_argument(
        "--base-ref",
        default="main",
        help="PR base branch ref (default: main).",
    )
    parser.add_argument(
        "--webhook-url",
        default=DEFAULT_WEBHOOK_URL,
        help=f"Webhook endpoint to POST to (default: {DEFAULT_WEBHOOK_URL}).",
    )
    parser.add_argument(
        "--mock-files-path",
        default=os.environ.get("BODHI_MOCK_PR_FILES_PATH", DEFAULT_MOCK_FILES_PATH),
        help=(
            "Path to the JSON fixture the backend reads via "
            "BODHI_MOCK_PR_FILES_PATH (default: $BODHI_MOCK_PR_FILES_PATH or "
            f"{DEFAULT_MOCK_FILES_PATH})."
        ),
    )
    parser.add_argument(
        "--allow-non-localhost",
        action="store_true",
        help=(
            "Permit posting to a non-loopback host. The script refuses by "
            "default so an accidental --webhook-url against a real backend "
            "can't decrypt and replay a live org's webhook secret."
        ),
    )
    return parser.parse_args()


def _guard_target_host(webhook_url: str, *, allow_non_localhost: bool) -> None:
    """Refuse non-loopback targets unless explicitly allowed.

    The script reads + decrypts a real org's webhook secret from the
    connected database. If that DB happens to point at a non-dev cluster
    and the webhook URL points at the matching prod backend, a single
    invocation would replay a signed merge event against production.
    Make that mistake impossible without an explicit flag.
    """
    host = (urlparse(webhook_url).hostname or "").lower()
    if host in _LOOPBACK_HOSTS:
        return
    if allow_non_localhost:
        print(
            f"warning: posting to non-loopback host '{host}' (allow-non-localhost set)",
            file=sys.stderr,
        )
        return
    sys.exit(
        f"error: refusing to POST to non-loopback host '{host}'. "
        "Pass --allow-non-localhost only if you genuinely intend to hit a "
        "remote backend with a signed webhook."
    )


async def _load_repo_and_secret(repo_id: uuid.UUID) -> tuple[TrackedRepository, str]:
    """Resolve the target repo + its org's decrypted webhook secret.

    Raises ``SystemExit`` (via ``sys.exit``) with a clear message rather
    than tracebacks for the expected-misuse cases (repo missing,
    secret unset/corrupted) — this is a dev tool, not a library.
    """
    async with AsyncSessionLocal() as db:
        repo = await db.get(TrackedRepository, repo_id)
        if repo is None:
            sys.exit(f"error: tracked repo {repo_id} not found")
        if not repo.github_repo_full_name:
            sys.exit(f"error: tracked repo {repo_id} has no github_repo_full_name")
        org = await db.get(Organization, repo.org_id)
        if org is None:
            sys.exit(f"error: org {repo.org_id} for repo {repo_id} not found")
        if not org.github_webhook_secret:
            sys.exit(f"error: org {org.id} has no github_webhook_secret configured")
        secret = decrypt_secret(org.github_webhook_secret)
        if not secret:
            sys.exit(f"error: org {org.id} webhook secret failed to decrypt")
        return repo, secret


def _build_payload(
    *,
    full_name: str,
    pr_number: int,
    base_sha: str,
    head_sha: str,
    base_ref: str,
) -> dict[str, Any]:
    """Minimal ``pull_request`` closed+merged payload the handler accepts.

    The backend parses the body with a Pydantic ``GitHubPullRequest``
    schema; this builder includes every field the merge path reads.
    Extra fields GitHub would send (review_comments, etc.) are omitted
    — Pydantic ignores unknowns on input.
    """
    owner, _, name = full_name.partition("/")
    merged_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return {
        "action": "closed",
        "pull_request": {
            "id": secrets.randbits(31),
            "number": pr_number,
            "merged": True,
            "merged_at": merged_at,
            "merge_commit_sha": head_sha,
            "title": f"mock PR #{pr_number}",
            # ``GitHubPullRequest`` requires ``html_url`` and ``state``; the
            # backend's schema validation rejects payloads missing either
            # field with HTTP 500 from the catch-all. Synthesise plausible
            # values rather than hand-waving with empty strings so the
            # dispatcher's later logging stays readable.
            "html_url": f"https://github.com/{full_name}/pull/{pr_number}",
            "state": "closed",
            "head": {"sha": head_sha, "ref": f"mock-pr-{pr_number}"},
            "base": {"sha": base_sha, "ref": base_ref},
            # ``user.id`` is required too — login alone is rejected.
            "user": {"login": "mock-author", "id": 0},
        },
        "repository": {
            "id": secrets.randbits(31),
            "full_name": full_name,
            "name": name,
            "owner": {"login": owner},
        },
    }


def _hmac_signature(secret: str, body: bytes) -> str:
    """Match the verifier at ``github_webhook._verify_github_signature``."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _write_mock_files_fixture(
    *,
    fixture_path: str,
    full_name: str,
    pr_number: int,
    changed_files: list[str],
) -> None:
    """Merge ``"<full_name>:<pr_number>" → [files]`` into the JSON fixture.

    Append-on-write keeps multi-scenario harness runs idempotent — each
    invocation adds its own key without clobbering prior ones, so a
    single ``BODHI_MOCK_PR_FILES_PATH`` value covers the whole session.
    """
    path = Path(fixture_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if path.exists():
        try:
            existing = json.loads(path.read_text()) or {}
        except json.JSONDecodeError:
            print(
                f"warning: {fixture_path} is not valid JSON — overwriting",
                file=sys.stderr,
            )
    existing[f"{full_name}:{pr_number}"] = changed_files
    path.write_text(json.dumps(existing, indent=2))


async def _post_webhook(*, url: str, body: bytes, signature: str, delivery_id: str) -> int:
    """POST the signed payload. Returns the HTTP status code."""
    headers = {
        "Content-Type": "application/json",
        "X-Hub-Signature-256": signature,
        "X-GitHub-Event": "pull_request",
        "X-GitHub-Delivery": delivery_id,
        "User-Agent": "bodhiorchard-mock-pr-webhook/1",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, content=body, headers=headers)
    print(f"→ POST {url} → {resp.status_code}")
    if resp.text:
        print(f"  body: {resp.text}")
    return resp.status_code


async def _amain() -> int:
    args = _parse_args()
    _guard_target_host(args.webhook_url, allow_non_localhost=args.allow_non_localhost)
    repo, secret = await _load_repo_and_secret(uuid.UUID(args.repo_id))
    full_name = repo.github_repo_full_name or ""
    # ``_load_repo_and_secret`` exits on a missing full_name, but assert
    # is stripped under -O so keep an explicit guard here too.
    if not full_name:
        sys.exit(f"error: repo {args.repo_id} has no github_repo_full_name")

    changed_files = [p.strip() for p in args.changed_files.split(",") if p.strip()]

    _write_mock_files_fixture(
        fixture_path=args.mock_files_path,
        full_name=full_name,
        pr_number=args.pr_number,
        changed_files=changed_files,
    )

    payload = _build_payload(
        full_name=full_name,
        pr_number=args.pr_number,
        base_sha=args.base_sha,
        head_sha=args.head_sha,
        base_ref=args.base_ref,
    )
    body = json.dumps(payload).encode()
    signature = _hmac_signature(secret, body)
    delivery_id = f"mock-{uuid.uuid4()}"

    print(f"→ wrote mock changed_files for {full_name}:{args.pr_number}")
    print(f"  fixture: {args.mock_files_path}")
    print(f"  files:   {changed_files or '(none)'}")
    print(
        "→ backend must have this in its environment to short-circuit GitHubClient.list_pr_files:"
    )
    print(f"     export BODHI_MOCK_PR_FILES_PATH={args.mock_files_path}")

    status = await _post_webhook(
        url=args.webhook_url,
        body=body,
        signature=signature,
        delivery_id=delivery_id,
    )
    return 0 if 200 <= status < 300 else 1


def main() -> int:
    """Sync entry point so the script is usable as a console_scripts target."""
    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())
