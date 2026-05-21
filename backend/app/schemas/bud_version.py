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

"""Pydantic DTOs for the BUD version history + revert endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class BUDVersionRead(BaseModel):
    """One row of BUD edit history.

    ``snapshot`` is intentionally omitted from the list view — it can
    weigh tens of KB per row and the UI only needs the summary line for
    the History tab. A future endpoint can return the full snapshot for
    a single (phase, version_no) when implementing the diff viewer.
    """

    id: uuid.UUID
    phase: str
    version_no: int
    source: str
    edited_by: uuid.UUID | None = None
    mcp_token_id: uuid.UUID | None = None
    reason: str | None = None
    edited_at: datetime

    model_config = {"from_attributes": True}
