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

"""When someone counts as having their own password (Generate vs Reset for HR)."""

from types import SimpleNamespace

from app.core.security import verify_password
from app.services.member_credentials import (
    chose_password,
    has_own_password,
    note_own_password,
    set_temporary_password,
)


def _user(*, must_change: bool = False, set_at: object = None) -> SimpleNamespace:
    return SimpleNamespace(
        password_hash="x", must_change_password=must_change, password_set_at=set_at
    )


def test_an_imported_account_has_never_set_one() -> None:
    assert not has_own_password(_user())  # type: ignore[arg-type]


def test_signing_in_with_a_temporary_password_does_not_count() -> None:
    user = _user(must_change=True)
    note_own_password(user)  # type: ignore[arg-type]
    assert not has_own_password(user)  # type: ignore[arg-type]


def test_signing_in_with_their_own_password_counts() -> None:
    user = _user()
    note_own_password(user)  # type: ignore[arg-type]
    assert has_own_password(user)  # type: ignore[arg-type]


def test_a_temporary_password_takes_it_away_until_they_choose_one() -> None:
    user = _user()
    chose_password(user, "Their-own-1")  # type: ignore[arg-type]
    assert has_own_password(user) and not user.must_change_password  # type: ignore[arg-type]
    temporary = set_temporary_password(user)  # type: ignore[arg-type]
    assert not has_own_password(user) and user.must_change_password  # type: ignore[arg-type]
    assert verify_password(temporary, user.password_hash)
