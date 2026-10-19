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

"""Telling an employee their bank or ID details changed.

Swapping someone's bank account is the classic payroll fraud, so the
employee always hears about it — in the app and on Slack — whoever made
the change. This alert can't be muted. It names the fields, never values.
"""

import uuid
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, NotificationType
from app.services.background import spawn
from app.services.event_bus import publish
from app.services.slack_dm import send_security_dm

LABELS = {
    "pan": "PAN",
    "aadhaar": "Aadhaar",
    "passport_number": "passport number",
    "bank_account_number": "bank account number",
    "bank_ifsc": "IFSC",
}


def alert_text(fields: set[str], changed_by: str) -> str:
    """The alert, e.g. "Your bank account number and IFSC were changed by Priya."."""
    names = [LABELS[f] for f in sorted(fields) if f in LABELS]
    listed = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"
    return (
        f"Your {listed} {'was' if len(names) == 1 else 'were'} changed by {changed_by}. "
        "If you didn't expect this, tell HR straight away."
    )


def stage_record_alert(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, text: str
) -> Callable[[], None]:
    """Add the in-app notification now; returns what to send once committed."""
    note = Notification(
        id=uuid.uuid4(),
        org_id=org_id,
        user_id=user_id,
        type=NotificationType.EMPLOYEE_RECORD_CHANGED,
        title="Your details changed",
        message=text,
        deep_link="/me/profile",
    )
    db.add(note)

    def send() -> None:
        publish(f"notifications:{user_id}", {"id": str(note.id), "type": note.type.value})
        spawn(send_security_dm(org_id, user_id, text))

    return send
