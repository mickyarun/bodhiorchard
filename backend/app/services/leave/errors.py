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

"""Why a leave action was refused, independent of HTTP.

Services raise these; the API maps each kind to a status code in one place
(:mod:`app.api.v1._leave_errors`). The message is always safe to show the
person who tried: it never carries another member's leave type or reason.
"""


class LeaveError(Exception):
    """A leave rule refused the action; ``str(exc)`` is the user-facing reason."""


class LeaveNotFoundError(LeaveError):
    """The request, policy or member doesn't exist in this org."""


class LeaveForbiddenError(LeaveError):
    """The caller may not do this to this request or member."""


class LeaveConflictError(LeaveError):
    """The current state doesn't allow it (already decided, no balance, …)."""


class LeaveInvalidError(LeaveError):
    """The input doesn't make sense for this member or policy."""


class LeaveRateLimitedError(LeaveError):
    """Too many attempts in a short time."""

    def __init__(self, message: str, *, retry_after_seconds: int) -> None:
        """Keep how long to wait, for the Retry-After header."""
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
