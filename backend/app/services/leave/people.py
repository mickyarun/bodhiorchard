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

"""Leave responses name people with their stored photo beside the name."""

from __future__ import annotations

import uuid
from collections.abc import Mapping

from app.repositories.user import PersonCard
from app.schemas.leave import PersonRef

__all__ = ["person_ref"]


def person_ref(
    user_id: uuid.UUID, people: Mapping[uuid.UUID, PersonCard], fallback: str
) -> PersonRef:
    """``PersonRef`` for ``user_id``, named ``fallback`` when the user is gone."""
    person = people.get(user_id)
    if person is None:
        return PersonRef(user_id=user_id, name=fallback)
    return PersonRef(user_id=user_id, name=person.name, avatar_url=person.avatar_url)
