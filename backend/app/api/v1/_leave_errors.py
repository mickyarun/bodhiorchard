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

"""Turn leave domain errors into HTTP responses, in one place."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.services.leave.errors import (
    LeaveConflictError,
    LeaveError,
    LeaveForbiddenError,
    LeaveInvalidError,
    LeaveNotFoundError,
    LeaveRateLimitedError,
)

_STATUS: tuple[tuple[type[LeaveError], int], ...] = (
    (LeaveNotFoundError, status.HTTP_404_NOT_FOUND),
    (LeaveForbiddenError, status.HTTP_403_FORBIDDEN),
    (LeaveConflictError, status.HTTP_409_CONFLICT),
    (LeaveInvalidError, status.HTTP_422_UNPROCESSABLE_ENTITY),
    (LeaveRateLimitedError, status.HTTP_429_TOO_MANY_REQUESTS),
)


def status_for(exc: LeaveError) -> int:
    """The HTTP status for a leave error (400 for an unclassified one)."""
    return next((code for kind, code in _STATUS if isinstance(exc, kind)), 400)


async def _respond(_request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, LeaveError):  # only ever registered for LeaveError
        raise exc
    headers = (
        {"Retry-After": str(exc.retry_after_seconds)}
        if isinstance(exc, LeaveRateLimitedError)
        else None
    )
    return JSONResponse({"detail": str(exc)}, status_code=status_for(exc), headers=headers)


def register_leave_errors(app: FastAPI) -> None:
    """Install the handler; call once wherever the API router is mounted."""
    app.add_exception_handler(LeaveError, _respond)
