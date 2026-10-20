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

"""Secrets that Full Docker generates per install (backend/docker/instance-secrets.sh).

Only Full Docker sets ``INSTANCE_SECRETS_DIR``. The entrypoint exports
the generated values to the server, but a process started separately
(``docker compose exec backend python -m scripts...``) only sees the
compose environment, where they're empty: it reads them from here so it
uses the same keys as the server. Production and Hybrid never set the
directory, so nothing here applies to them.
"""

import os
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

# The default every Full Docker install used before keys were per install.
# Kept readable there so anything still under it gets re-encrypted.
LEGACY_ENCRYPTION_KEY = "change-me-encryption-key"


def enabled() -> bool:
    """True in Full Docker, where secrets are generated per install."""
    return bool(os.environ.get("INSTANCE_SECRETS_DIR"))


def read(name: str, *, directory_env: str = "INSTANCE_SECRETS_DIR") -> str | None:
    """This install's generated secret ``name``, or None.

    The bridge secret lives in ``BRIDGE_SECRET_DIR`` (its own volume, shared
    with the multiplayer container); everything else in the main directory.
    """
    base = os.environ.get(directory_env) or os.environ.get("INSTANCE_SECRETS_DIR")
    if not base:
        return None
    path = Path(base) / name
    try:
        value = path.read_text().strip()
    except FileNotFoundError:
        return None
    except OSError as exc:
        # Present but unreadable: say so, or settings quietly fall back to
        # the shared default key.
        logger.warning("instance_secret_unreadable", path=str(path), error=type(exc).__name__)
        return None
    return value or None
