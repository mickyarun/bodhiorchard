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

"""A stored personal email is shown as saved; only the edit forms check it."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.schemas.employee import EmployeePersonal, EmployeePersonalRead

LOOSE = "me@laptop.local"


def test_read_model_shows_a_stored_address_the_validator_would_refuse() -> None:
    row = SimpleNamespace(personal_email=LOOSE)

    assert EmployeePersonalRead.model_validate(row).personal_email == LOOSE


def test_the_edit_model_still_refuses_it() -> None:
    with pytest.raises(ValidationError):
        EmployeePersonal(personal_email=LOOSE)
