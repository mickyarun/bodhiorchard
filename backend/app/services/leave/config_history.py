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

"""Reading a policy's configuration trail, with who made each change."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_policy import LeavePolicy
from app.repositories.leave_config_event import LeaveConfigEventRepository
from app.repositories.user import UserRepository
from app.schemas.leave import PersonRef
from app.schemas.leave_config import ConfigEventRead


async def config_history(db: AsyncSession, policy: LeavePolicy) -> list[ConfigEventRead]:
    """The policy's recent changes, newest first."""
    events = await LeaveConfigEventRepository(db, org_id=policy.org_id).for_policy(policy.id)
    names = await UserRepository(db).get_names_by_ids({e.actor_id for e in events})
    return [
        ConfigEventRead(
            id=event.id,
            action=event.action,
            actor=PersonRef(user_id=event.actor_id, name=names.get(event.actor_id, "Someone")),
            at=event.created_at,
            changes=event.changes,
        )
        for event in events
    ]
