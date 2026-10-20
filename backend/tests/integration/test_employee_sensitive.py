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

"""Sensitive details and documents over HTTP: who sees what, what's stored,
what's logged."""

from __future__ import annotations

import base64
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from pydantic import SecretStr
from sqlalchemy import select, text

from app.config import settings
from app.core import hr_crypto
from app.models.employee_audit_event import EmployeeAuditEvent
from app.models.employee_document import EmployeeDocument
from app.models.employee_sensitive import EmployeeSensitiveDetails
from app.models.notification import Notification, NotificationType
from app.services.employees import documents, hr_key_rotation, record_alerts
from app.services.employees.document_policy import MAX_DOCUMENT_BYTES
from app.services.file_storage import FileStorage
from tests.integration.leave_support import Factory, as_user, give_role, setup_org

pytestmark = pytest.mark.integration
BASE = "/api/v1/employees"
PDF = b"%PDF-1.7\n1 0 obj << /Type /Catalog >> endobj\n%%EOF"


@pytest.fixture
def hr_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FileStorage:
    """A configured HR key, and document storage in a temp folder."""
    key = base64.b64encode(b"k" * 32).decode()
    monkeypatch.setattr(settings.hr_crypto, "hr_encryption_keys", SecretStr(f"test:{key}"))
    hr_crypto._configured_keyring.cache_clear()
    storage = FileStorage()
    storage.local_dir = tmp_path
    monkeypatch.setattr(documents, "get_file_storage", lambda: storage)
    monkeypatch.setattr(hr_key_rotation, "get_file_storage", lambda: storage)
    monkeypatch.setattr(record_alerts, "spawn", lambda job: job.close())
    return storage


async def _team(factory: Factory) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    org, (emp, hr, dev), _ = await setup_org(factory, "Emp", "Hr", "Dev")
    await give_role(factory, org, hr, "hr")
    await give_role(factory, org, dev, "developer")
    return org, emp, hr, dev


async def test_only_hr_and_the_employee_see_details(
    client: AsyncClient, pg_session_factory: Factory, hr_key: FileStorage
) -> None:
    org, emp, hr, dev = await _team(pg_session_factory)
    url = f"{BASE}/{emp}/sensitive"
    for viewer, expected in ((emp, 200), (hr, 200), (dev, 403)):
        assert (await client.get(url, headers=as_user(viewer, org))).status_code == expected
    docs = f"{BASE}/{emp}/documents"
    assert (await client.get(docs, headers=as_user(dev, org))).status_code == 403


async def test_values_are_stored_encrypted_masked_on_read_and_revealed_with_a_log(
    client: AsyncClient, pg_session_factory: Factory, hr_key: FileStorage
) -> None:
    org, emp, hr, _dev = await _team(pg_session_factory)
    body = {"bank_account_number": "001234567890", "bank_ifsc": "HDFC0001234", "pan": "ABCDE1234F"}
    saved = await client.put(f"{BASE}/{emp}/sensitive", json=body, headers=as_user(hr, org))
    assert saved.status_code == 200, saved.text
    data = saved.json()
    assert data["bank_account_number"] == {"is_set": True, "last4": "7890"}
    assert "001234567890" not in saved.text
    async with pg_session_factory() as db:
        row = (await db.execute(select(EmployeeSensitiveDetails))).scalars().all()
        stored = next(r for r in row if r.org_id == org)
        assert stored.bank_account_number and b"001234567890" not in stored.bank_account_number
        alerts = (
            (
                await db.execute(
                    select(Notification).where(
                        Notification.user_id == emp,
                        Notification.type == NotificationType.EMPLOYEE_RECORD_CHANGED,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(alerts) == 1 and "Hr" in alerts[0].message and "7890" not in alerts[0].message
    revealed = await client.post(
        f"{BASE}/{emp}/sensitive/reveal",
        json={"field": "bank_account_number"},
        headers=as_user(emp, org),
    )
    assert revealed.json() == {"field": "bank_account_number", "value": "001234567890"}
    log = (await client.get(f"{BASE}/{emp}/access-log", headers=as_user(emp, org))).json()
    assert [e["action"] for e in log] == ["field_revealed", "details_updated"]


async def test_no_key_means_503_not_plaintext(
    client: AsyncClient, pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org, emp, hr, _dev = await _team(pg_session_factory)
    monkeypatch.setattr(settings.hr_crypto, "hr_encryption_keys", SecretStr(""))
    hr_crypto._configured_keyring.cache_clear()
    response = await client.put(
        f"{BASE}/{emp}/sensitive", json={"pan": "ABCDE1234F"}, headers=as_user(hr, org)
    )
    assert response.status_code == 503
    assert "HR_ENCRYPTION_KEYS" in response.json()["detail"]


async def test_documents_are_encrypted_at_rest_and_only_hr_deletes(
    client: AsyncClient, pg_session_factory: Factory, hr_key: FileStorage
) -> None:
    org, emp, hr, _dev = await _team(pg_session_factory)
    files = {"file": ("offer.pdf", PDF, "application/pdf")}
    uploaded = await client.post(
        f"{BASE}/{emp}/documents",
        data={"doc_type": "offer_letter"},
        files=files,
        headers=as_user(emp, org),
    )
    assert uploaded.status_code == 201, uploaded.text
    doc_id = uploaded.json()["id"]
    on_disk = list(Path(hr_key.local_dir).rglob("*.bin"))
    assert len(on_disk) == 1 and not on_disk[0].read_bytes().startswith(b"%PDF")
    opened = await client.get(f"{BASE}/documents/{doc_id}/content", headers=as_user(hr, org))
    assert opened.content == PDF
    assert opened.headers["cache-control"] == "no-store, private"
    assert opened.headers["x-content-type-options"] == "nosniff"
    disguised = {"file": ("payslip.pdf", b"MZ fake exe", "application/pdf")}
    rejected = await client.post(
        f"{BASE}/{emp}/documents",
        data={"doc_type": "payslip"},
        files=disguised,
        headers=as_user(emp, org),
    )
    assert rejected.status_code == 422
    # The list says the cap; one byte over it is refused before storage.
    listed = await client.get(f"{BASE}/{emp}/documents", headers=as_user(emp, org))
    assert listed.json()["max_upload_bytes"] == MAX_DOCUMENT_BYTES
    too_big = {
        "file": ("scan.pdf", PDF + b"0" * (MAX_DOCUMENT_BYTES + 1 - len(PDF)), "application/pdf")
    }
    over = await client.post(
        f"{BASE}/{emp}/documents",
        data={"doc_type": "id_proof"},
        files=too_big,
        headers=as_user(emp, org),
    )
    assert over.status_code == 422 and "10 MB" in over.json()["detail"]
    assert len(list(Path(hr_key.local_dir).rglob("*.bin"))) == 1
    delete = f"{BASE}/documents/{doc_id}"
    assert (await client.delete(delete, headers=as_user(emp, org))).status_code == 403
    assert (await client.delete(delete, headers=as_user(hr, org))).status_code == 204
    async with pg_session_factory() as db:
        assert await db.get(EmployeeDocument, uuid.UUID(doc_id)) is None
        actions = (
            (
                await db.execute(
                    select(EmployeeAuditEvent.action).where(
                        EmployeeAuditEvent.subject_user_id == emp
                    )
                )
            )
            .scalars()
            .all()
        )
        assert {a.value for a in actions} == {
            "document_uploaded",
            "document_viewed",
            "document_deleted",
        }


async def test_access_log_cannot_be_rewritten(
    client: AsyncClient, pg_session_factory: Factory, hr_key: FileStorage
) -> None:
    org, emp, hr, _dev = await _team(pg_session_factory)
    await client.post(
        f"{BASE}/{emp}/sensitive/reveal", json={"field": "pan"}, headers=as_user(hr, org)
    )
    async with pg_session_factory() as db:
        with pytest.raises(Exception, match="append-only"):
            await db.execute(
                text("update employee_audit_events set target = 'x' where subject_user_id = :u"),
                {"u": emp},
            )


async def test_access_log_follows_the_record_through_a_merge(
    client: AsyncClient, pg_session_factory: Factory, hr_key: FileStorage
) -> None:
    org, emp, hr, _dev = await _team(pg_session_factory)
    _org2, (survivor,), _ = await setup_org(pg_session_factory, "Survivor")
    async with pg_session_factory() as db:
        await db.execute(
            text(
                "insert into org_to_user (id, user_id, org_id) values (gen_random_uuid(), :u, :o)"
            ),
            {"u": survivor, "o": org},
        )
        await db.commit()
    await client.post(
        f"{BASE}/{emp}/sensitive/reveal", json={"field": "pan"}, headers=as_user(hr, org)
    )
    async with pg_session_factory() as db:
        # What a member merge does: the record moves to the surviving account.
        await db.execute(
            text("update employee_profiles set user_id = :s where user_id = :e and org_id = :o"),
            {"s": survivor, "e": emp, "o": org},
        )
        await db.commit()
    log = await client.get(f"{BASE}/{survivor}/access-log", headers=as_user(hr, org))
    assert [e["action"] for e in log.json()] == ["field_revealed"]


async def test_rotation_moves_everything_to_the_new_key(
    client: AsyncClient,
    pg_session_factory: Factory,
    hr_key: FileStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org, emp, hr, _dev = await _team(pg_session_factory)
    old = settings.hr_crypto.hr_encryption_keys.get_secret_value()
    await client.put(
        f"{BASE}/{emp}/sensitive", json={"pan": "ABCDE1234F"}, headers=as_user(hr, org)
    )
    form = {"doc_type": "other"}
    files = {"file": ("a.pdf", PDF, "application/pdf")}
    await client.post(f"{BASE}/{emp}/documents", data=form, files=files, headers=as_user(emp, org))
    new = base64.b64encode(b"n" * 32).decode()
    monkeypatch.setattr(settings.hr_crypto, "hr_encryption_keys", SecretStr(f"new:{new},{old}"))
    hr_crypto._configured_keyring.cache_clear()
    async with pg_session_factory() as db:
        first = await hr_key_rotation.rotate(db, dry_run=False)
    async with pg_session_factory() as db:
        again = await hr_key_rotation.rotate(db, dry_run=True)
    assert first.fields >= 1 and first.documents >= 1 and not first.failed
    assert (again.fields, again.documents) == (0, 0)
    revealed = await client.post(
        f"{BASE}/{emp}/sensitive/reveal", json={"field": "pan"}, headers=as_user(hr, org)
    )
    assert revealed.json()["value"] == "ABCDE1234F"
