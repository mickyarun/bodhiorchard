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

"""FastAPI dependency injection providers — the stable import surface.

Identity resolution lives in :mod:`app.core.auth_deps`; permission
resolution and checks live in :mod:`app.core.permission_deps`. Handlers
keep importing from here.
"""

from app.core.auth_deps import (
    get_current_user,
    get_current_user_pending_password,
    get_db,
    oauth2_scheme,
)
from app.core.permission_deps import (
    PermissionSet,
    get_permission_set,
    get_user_permissions,
    is_org_owner,
    member_has_permission,
    require_permissions,
)

__all__ = [
    "PermissionSet",
    "get_current_user",
    "get_current_user_pending_password",
    "get_db",
    "get_permission_set",
    "get_user_permissions",
    "is_org_owner",
    "member_has_permission",
    "oauth2_scheme",
    "require_permissions",
]
