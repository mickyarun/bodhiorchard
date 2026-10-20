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

"""Who may see, reveal and change sensitive details and documents (pure).

HR (employees:manage for details, employees:documents for documents),
the org owner (who holds every permission), and the employee for their
own record. Engineering roles — DevOps, developers, admins without these
permissions — get nothing. Only HR deletes documents.
"""

import uuid
from dataclasses import dataclass

from app.core.permission_deps import PermissionSet
from app.services.employees.access import MANAGE

DOCUMENTS = "employees:documents"


@dataclass(frozen=True)
class SensitiveAccess:
    """The caller's rights over one person's sensitive details and documents."""

    details: bool
    documents: bool
    delete_documents: bool


def sensitive_access(
    perms: PermissionSet, actor_id: uuid.UUID, subject_id: uuid.UUID
) -> SensitiveAccess:
    """Resolve the caller's rights over ``subject_id``'s sensitive records."""
    is_self = actor_id == subject_id
    return SensitiveAccess(
        details=is_self or perms.has(MANAGE),
        documents=is_self or perms.has(DOCUMENTS),
        delete_documents=perms.has(DOCUMENTS),
    )
