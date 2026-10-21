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

"""DTOs for HR generating or resetting someone's sign-in password."""

from typing import Literal

from pydantic import BaseModel, Field

PasswordAction = Literal["generate", "reset"]


class EmployeeLoginRead(BaseModel):
    """What HR's password button offers for this person."""

    # "generate" while they've never set their own password, else "reset".
    action: PasswordAction
    email: str
    slack_linked: bool


class EmployeePasswordRequest(BaseModel):
    """Optionally DM the new password on Slack in the same call."""

    send_via: Literal["slack"] | None = None


class EmployeePasswordResult(BaseModel):
    """The new temporary password, shown to HR once and never stored in plain text."""

    action: PasswordAction
    password: str = Field(..., description="Sensitive: shown once.")
    login_url: str
    slack_sent: bool | None = None
    slack_error: str | None = None
