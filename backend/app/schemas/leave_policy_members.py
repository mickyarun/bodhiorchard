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

"""DTOs for who follows which leave policy (leave:configure)."""

import uuid
from datetime import date

from pydantic import BaseModel


class PolicyMemberRead(BaseModel):
    """One employee and the leave policy they follow.

    ``explicit`` is False for people nobody has assigned: they follow the
    default policy, whose id and name are filled in for them.
    ``assigned_on`` is set only for a real transfer between policies; until
    then the employee's joining date drives their allocation.
    """

    user_id: uuid.UUID
    name: str
    email: str
    department: str | None
    policy_id: uuid.UUID
    policy_name: str
    explicit: bool
    assigned_on: date | None
