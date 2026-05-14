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

"""Unit tests for the role-validation predicate.

Pure helper, no DB. The HTTP wrapper that translates ``False`` into a
400 lives in ``app/api/v1/roles.py`` and is exercised by
``tests/api/v1/test_roles_base_role_validation.py``.
"""

from types import SimpleNamespace

import pytest

from app.models.role import RoleScopeType
from app.services.role_validation import is_valid_base_role


def _role(scope_type: RoleScopeType, *, is_active: bool = True) -> SimpleNamespace:
    return SimpleNamespace(scope_type=scope_type, is_active=is_active)


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (None, False),
        (_role(RoleScopeType.SYSTEM, is_active=True), True),
        (_role(RoleScopeType.SYSTEM, is_active=False), False),
        (_role(RoleScopeType.CUSTOM, is_active=True), False),
        (_role(RoleScopeType.CUSTOM, is_active=False), False),
    ],
)
def test_is_valid_base_role(role: SimpleNamespace | None, expected: bool) -> None:
    """Only active SYSTEM roles are valid inheritance targets."""
    assert is_valid_base_role(role) is expected
