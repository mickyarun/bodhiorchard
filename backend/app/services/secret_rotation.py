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

"""Re-encrypting stored integration secrets under the current ENCRYPTION_KEY.

Encrypted values are strings starting with ``enc:`` (see
:mod:`app.core.encryption`). They live on organizations: in text columns
(Slack, GitHub, Claude keys) and inside the ``config`` JSON (Jira token,
cloud LLM key). Rather than list them, every text column and every string
in the config is checked, so a secret added later is rotated too.

Values already under the current key are skipped, so it's safe to run
again after an interruption; everything is saved in one transaction.
"""

from dataclasses import dataclass, field
from typing import Any

from cryptography.fernet import InvalidToken
from sqlalchemy import String, Text, inspect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import reencrypt_secret
from app.models.organization import Organization
from app.repositories.secret_rotation import SecretRotationRepository

# Text columns on organizations that may hold an encrypted value.
_TEXT_COLUMNS = tuple(
    attr.key
    for attr in inspect(Organization).column_attrs
    if isinstance(attr.columns[0].type, (String, Text))
)


@dataclass
class RotationReport:
    """How many secrets were re-encrypted, and which couldn't be read."""

    rotated: int = 0
    failed: list[str] = field(default_factory=list)


def _rotate_value(value: Any, where: str, report: RotationReport) -> Any:
    """``value`` with every encrypted string under the current key."""
    if isinstance(value, dict):
        return {key: _rotate_value(item, f"{where}.{key}", report) for key, item in value.items()}
    if isinstance(value, list):
        return [_rotate_value(item, f"{where}[{i}]", report) for i, item in enumerate(value)]
    if not isinstance(value, str):
        return value
    try:
        fresh = reencrypt_secret(value)
    except InvalidToken:
        # No configured key reads it: leave it alone and say where it is.
        report.failed.append(where)
        return value
    if fresh is None:
        return value
    report.rotated += 1
    return fresh


async def rotate(db: AsyncSession, *, dry_run: bool) -> RotationReport:
    """Re-encrypt every organization secret not under the current key."""
    report = RotationReport()
    for org in await SecretRotationRepository(db).all_organizations():
        label = f"org {org.id}"
        for column in _TEXT_COLUMNS:
            value = getattr(org, column)
            fresh = _rotate_value(value, f"{label} {column}", report)
            if fresh is not value and not dry_run:
                setattr(org, column, fresh)
        config = org.config or {}
        fresh_config = _rotate_value(config, f"{label} config", report)
        if fresh_config != config and not dry_run:
            org.config = fresh_config
    if not dry_run:
        await db.commit()
    return report
