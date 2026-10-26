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

"""An invite's photo URL is loaded by every viewer and by Slack: https only."""

import pytest
from pydantic import ValidationError

from app.schemas.members import AddMemberRequest

BASE = {"email": "a@b.dev", "name": "A", "password": "secret1"}


def test_https_url_is_kept() -> None:
    url = "https://avatars.githubusercontent.com/u/1"
    assert AddMemberRequest(**BASE, avatarUrl=url).avatar_url == url


@pytest.mark.parametrize("value", [None, "", "   "])
def test_blank_means_no_photo(value: str | None) -> None:
    assert AddMemberRequest(**BASE, avatarUrl=value).avatar_url is None


@pytest.mark.parametrize(
    "value",
    [
        "javascript:alert(1)",
        "data:image/png;base64,AAAA",
        "http://example.com/a.png",
        "/api/v1/employees/avatars/abc",
        "https://",
    ],
)
def test_anything_else_is_refused(value: str) -> None:
    with pytest.raises(ValidationError):
        AddMemberRequest(**BASE, avatarUrl=value)
