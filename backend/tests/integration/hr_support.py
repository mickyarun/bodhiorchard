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

"""One HR encryption key and document store for the people integration tests.

Every module that saves sensitive details or documents must use this key: the
key-rotation test re-keys every row in the shared database, so a row written
under another key with the same key id would fail its integrity check there.
"""

from __future__ import annotations

import base64
import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from pydantic import SecretStr

from app.config import settings
from app.core import hr_crypto
from app.services.employees import documents, hr_key_rotation, record_alerts
from app.services.file_storage import FileStorage
from tests.integration.leave_support import Factory, as_user, give_role, report_to, setup_org

PEOPLE = "/api/v1/employees"
PDF = b"%PDF-1.7\n1 0 obj << /Type /Catalog >> endobj\n%%EOF"
TEST_KEY = base64.b64encode(b"k" * 32).decode()


def configure_hr_storage(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FileStorage:
    """Set the test HR key and keep documents in ``tmp_path``; alerts are not sent."""
    monkeypatch.setattr(settings.hr_crypto, "hr_encryption_keys", SecretStr(f"test:{TEST_KEY}"))
    hr_crypto._configured_keyring.cache_clear()
    storage = FileStorage()
    storage.local_dir = tmp_path
    monkeypatch.setattr(documents, "get_file_storage", lambda: storage)
    monkeypatch.setattr(hr_key_rotation, "get_file_storage", lambda: storage)
    monkeypatch.setattr(record_alerts, "spawn", lambda job: job.close())
    return storage


async def seed_employee(
    client: AsyncClient, factory: Factory
) -> tuple[uuid.UUID, dict[str, uuid.UUID]]:
    """An employee with a saved PAN and one HR-uploaded document, HR, and their manager.

    Returns ``(org, {"emp", "hr", "mgr", "doc"})``. Needs
    :func:`configure_hr_storage` first; delete the document when done (the
    key-rotation test cannot reach another test's document storage).
    """
    org, (emp, hr, mgr), _ = await setup_org(factory, "Emp", "Hr", "Mgr")
    await give_role(factory, org, hr, "hr")
    await give_role(factory, org, mgr, "manager")
    await report_to(factory, org, emp, mgr)
    headers = as_user(hr, org)
    saved = await client.put(
        f"{PEOPLE}/{emp}/sensitive", json={"pan": "ABCDE1234F"}, headers=headers
    )
    assert saved.status_code == 200, saved.text
    uploaded = await client.post(
        f"{PEOPLE}/{emp}/documents",
        data={"doc_type": "id_proof"},
        files={"file": ("pan.pdf", PDF, "application/pdf")},
        headers=headers,
    )
    assert uploaded.status_code == 201, uploaded.text
    doc = uuid.UUID(uploaded.json()["id"])
    return org, {"emp": emp, "hr": hr, "mgr": mgr, "doc": doc}
