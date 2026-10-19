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

"""Each kind of leave error becomes one HTTP status."""

import pytest

from app.api.v1._leave_errors import status_for
from app.services.leave.errors import (
    LeaveConflictError,
    LeaveError,
    LeaveForbiddenError,
    LeaveInvalidError,
    LeaveNotFoundError,
    LeaveRateLimitedError,
)
from app.services.leave.holidays import HolidayImportError


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (LeaveNotFoundError("x"), 404),
        (LeaveForbiddenError("x"), 403),
        (LeaveConflictError("x"), 409),
        (LeaveInvalidError("x"), 422),
        (HolidayImportError("x"), 422),
        (LeaveRateLimitedError("x", retry_after_seconds=60), 429),
        (LeaveError("x"), 400),
    ],
)
def test_status_for(error: LeaveError, status: int) -> None:
    assert status_for(error) == status
