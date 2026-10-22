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

"""Avatar routes: who may write, what gets stored, what the public GET reveals."""

from __future__ import annotations

import io
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi import HTTPException
from PIL import Image

from app.api.router import api_router
from app.api.v1 import employee_avatars as routes

ORG = uuid.uuid4()
ME = uuid.uuid4()
SOMEONE_ELSE = uuid.uuid4()


def _png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (40, 40), (10, 120, 200)).save(out, format="PNG")
    return out.getvalue()


@dataclass
class _Perms:
    granted: set[str] = field(default_factory=set)
    is_owner: bool = False

    def has(self, permission: str) -> bool:
        return self.is_owner or permission in self.granted

    def has_all(self, permissions: Any) -> bool:
        return all(self.has(p) for p in permissions)

    def has_any(self, permissions: Any) -> bool:
        return any(self.has(p) for p in permissions)


@dataclass
class _User:
    id: uuid.UUID
    org_id: uuid.UUID = ORG
    name: str = "Member"
    slack_id: str | None = None
    avatar_url: str | None = None
    avatar_storage_path: str | None = None
    avatar_key: str | None = None


class _Upload:
    def __init__(self, data: bytes, filename: str = "me.png") -> None:
        self._data = data
        self.filename = filename

    async def read(self, size: int = -1) -> bytes:
        return self._data if size < 0 else self._data[:size]


class _Db:
    async def flush(self) -> None:
        return None


@dataclass
class _Storage:
    files: dict[str, bytes] = field(default_factory=dict)
    deleted: list[str] = field(default_factory=list)

    async def upload(self, *, org_id: str, relative_path: str, data: bytes, **kw: Any) -> str:
        path = f"{org_id}/{relative_path}"
        self.files[path] = data
        return path

    async def download(self, path: str) -> tuple[bytes, str]:
        return self.files[path], "application/octet-stream"

    async def delete(self, path: str) -> None:
        self.deleted.append(path)
        self.files.pop(path, None)


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    users = {ME: _User(ME), SOMEONE_ELSE: _User(SOMEONE_ELSE)}
    storage = _Storage()

    class _Repo:
        def __init__(self, db: Any, org_id: Any = None) -> None:
            pass

        async def get_by_id_with_membership(self, uid: uuid.UUID, org_id: uuid.UUID) -> Any:
            return users.get(uid)

        async def get_by_avatar_key(self, key: str) -> Any:
            return next((u for u in users.values() if u.avatar_key == key), None)

    monkeypatch.setattr(routes, "UserRepository", _Repo)
    monkeypatch.setattr(routes, "get_file_storage", lambda: storage)
    return {"users": users, "storage": storage, "me": _User(ME)}


async def _upload(env: dict[str, Any], target: uuid.UUID, data: bytes, perms: _Perms) -> Any:
    return await routes.upload_avatar(
        target, _Upload(data), current_user=env["me"], perms=perms, db=_Db()
    )


class TestWritePermissions:
    async def test_member_can_change_their_own_photo(self, env: dict[str, Any]) -> None:
        result = await _upload(env, ME, _png(), _Perms())
        assert result.avatar_url.startswith("/api/v1/employees/avatars/")

    async def test_member_cannot_change_someone_elses(self, env: dict[str, Any]) -> None:
        with pytest.raises(HTTPException) as exc:
            await _upload(env, SOMEONE_ELSE, _png(), _Perms())
        assert exc.value.status_code == 403

    async def test_hr_can_change_anyones(self, env: dict[str, Any]) -> None:
        result = await _upload(env, SOMEONE_ELSE, _png(), _Perms({"employees:manage"}))
        assert result.avatar_url


class TestUpload:
    async def test_url_carries_the_key_not_the_user_id(self, env: dict[str, Any]) -> None:
        result = await _upload(env, ME, _png(), _Perms())
        assert str(ME) not in result.avatar_url
        assert env["users"][ME].avatar_key in result.avatar_url

    async def test_stored_bytes_are_re_encoded_jpeg(self, env: dict[str, Any]) -> None:
        await _upload(env, ME, _png(), _Perms())
        stored = env["storage"].files[env["users"][ME].avatar_storage_path]
        assert Image.open(io.BytesIO(stored)).format == "JPEG"

    async def test_renamed_non_image_is_rejected(self, env: dict[str, Any]) -> None:
        with pytest.raises(HTTPException) as exc:
            await _upload(env, ME, b"<script>alert(1)</script>", _Perms())
        assert exc.value.status_code == 400
        assert env["storage"].files == {}

    async def test_replacing_deletes_the_previous_file(self, env: dict[str, Any]) -> None:
        await _upload(env, ME, _png(), _Perms())
        first = env["users"][ME].avatar_storage_path
        await _upload(env, ME, _png(), _Perms())
        second = env["users"][ME].avatar_storage_path
        assert first != second
        assert env["storage"].deleted == [first]
        assert list(env["storage"].files) == [second]

    async def test_delete_clears_row_and_file(self, env: dict[str, Any]) -> None:
        await _upload(env, ME, _png(), _Perms())
        path = env["users"][ME].avatar_storage_path
        await routes.delete_avatar(ME, current_user=env["me"], perms=_Perms(), db=_Db())
        user = env["users"][ME]
        assert (user.avatar_url, user.avatar_key, user.avatar_storage_path) == (None, None, None)
        assert env["storage"].deleted == [path]


class TestPublicServe:
    async def test_serves_jpeg_with_hardening_headers(self, env: dict[str, Any]) -> None:
        await _upload(env, ME, _png(), _Perms())
        response = await routes.serve_avatar(env["users"][ME].avatar_key, db=_Db())
        assert response.media_type == "image/jpeg"
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert "sandbox" in response.headers["Content-Security-Policy"]

    @pytest.mark.parametrize("key", ["nope", "0" * 32, str(uuid.uuid4()), "../../etc/passwd"])
    async def test_unknown_or_malformed_keys_all_404(self, env: dict[str, Any], key: str) -> None:
        with pytest.raises(HTTPException) as exc:
            await routes.serve_avatar(key, db=_Db())
        assert exc.value.status_code == 404

    async def test_old_key_stops_working_after_replace(self, env: dict[str, Any]) -> None:
        await _upload(env, ME, _png(), _Perms())
        old_key = env["users"][ME].avatar_key
        await _upload(env, ME, _png(), _Perms())
        with pytest.raises(HTTPException):
            await routes.serve_avatar(old_key, db=_Db())


def test_slack_photo_import_is_open_to_hr_and_admins() -> None:
    """HR or admins/owner run the import — not integrations:configure."""
    route = next(
        r
        for r in api_router.routes
        if getattr(r, "path", "") == "/api/v1/employees/avatars/sync-slack"
    )
    required: set[str] = set()
    for dep in route.dependencies:  # type: ignore[attr-defined]
        required.update(getattr(dep.dependency, "required_permissions", ()))
    assert required == {"employees:manage", "org:edit_settings"}
