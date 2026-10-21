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


"""HR invites new hires from the People workspace, within its own grants."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.user import User
from tests.integration.leave_support import Factory, as_user, give_role, setup_org

pytestmark = pytest.mark.integration


async def test_hr_invites_a_new_hire_who_must_set_their_own_password(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (hr,), _ = await setup_org(pg_session_factory, "Hr")
    await give_role(pg_session_factory, org, hr, "hr")
    headers = as_user(hr, org)
    roles = {
        r["name"]: r["id"] for r in (await client.get("/api/v1/roles", headers=headers)).json()
    }

    def invite(email: str, role: str | None) -> dict[str, object]:
        body: dict[str, object] = {
            "email": email, "name": "New Hire", "password": "Temp-12345",
            "mustChangePassword": True,
        }  # fmt: skip
        if role:
            body["roleId"] = roles[role]
        return body

    created = await client.post(
        "/api/v1/members", json=invite("hire@acme.dev", "sales"), headers=headers
    )
    assert created.status_code == 201, created.text
    async with pg_session_factory() as db:
        user = await db.get(User, uuid.UUID(created.json()["id"]))
        assert user is not None and user.must_change_password is True
    # HR onboards engineers too, with a role or none...
    for email, role in (("dev@acme.dev", "developer"), ("norole@acme.dev", None)):
        made = await client.post("/api/v1/members", json=invite(email, role), headers=headers)
        assert made.status_code == 201, (role, made.text)
    # ...but never anyone who could manage members, roles or settings.
    for email, role in (("admin@acme.dev", "admin"), ("mgr@acme.dev", "manager")):
        refused = await client.post("/api/v1/members", json=invite(email, role), headers=headers)
        assert refused.status_code == 403, (role, refused.text)
    # The invite dialog offers exactly what the server allows.
    assignable = (await client.get("/api/v1/roles/assignable", headers=headers)).json()
    offered = {name for name, rid in roles.items() if rid in assignable}
    assert {"developer", "qa", "pm", "tech_lead", "hr", "sales"} <= offered
    assert not offered & {"admin", "manager", "org_owner"}
