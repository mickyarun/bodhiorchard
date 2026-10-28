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

"""Turn a refused GitHub API call into an HTTP error the settings UI can act on.

The App-installation helpers raise ``httpx.HTTPStatusError`` when GitHub
answers 4xx/5xx. Left alone that escapes a route as a bare 500, which the
repo picker can only show as "something went wrong". :func:`explain_github_errors`
wraps the call and answers instead with a status and a sentence saying what
to do: wait out a rate limit, fix the App's permissions, or retry later.
"""

from collections.abc import Iterator
from contextlib import contextmanager

import structlog
from fastapi import HTTPException, status
from httpx import HTTPStatusError, Response

logger = structlog.get_logger(__name__)

RATE_LIMITED = "GitHub's API rate limit for this App is used up. Try again in a few minutes."
NO_ACCESS = (
    "GitHub refused the App's request. Check that the App is still installed and "
    "can read the organization's repositories."
)
UNAVAILABLE = "GitHub did not answer the request. Try again in a moment."


def _rate_limited(resp: Response) -> bool:
    """GitHub's primary (``X-RateLimit-Remaining: 0``) or secondary (429) limit."""
    if resp.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        return True
    return (
        resp.status_code == status.HTTP_403_FORBIDDEN
        and resp.headers.get("x-ratelimit-remaining") == "0"
    )


def github_upstream_error(resp: Response) -> HTTPException:
    """The HTTP error to answer with for GitHub's failed ``resp``."""
    logger.warning("github_upstream_error", status=resp.status_code)
    if _rate_limited(resp):
        return HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=RATE_LIMITED)
    if resp.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=NO_ACCESS)
    return HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=UNAVAILABLE)


@contextmanager
def explain_github_errors() -> Iterator[None]:
    """Re-raise a GitHub ``HTTPStatusError`` inside the block as an explained ``HTTPException``."""
    try:
        yield
    except HTTPStatusError as exc:
        raise github_upstream_error(exc.response) from exc
