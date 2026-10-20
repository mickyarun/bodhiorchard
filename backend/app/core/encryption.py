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

"""Symmetric encryption for secrets stored in the database.

Uses Fernet (AES-128-CBC + HMAC-SHA256) with a key derived from the
ENCRYPTION_KEY environment variable via PBKDF2.

Rotation: set ENCRYPTION_KEY to the new key and ENCRYPTION_KEY_PREVIOUS
to the old one(s). Both stay readable; new values use the new key, and
``scripts/rotate_encryption_key.py`` re-encrypts the rest. Once it
reports nothing left, drop ENCRYPTION_KEY_PREVIOUS.
"""

import base64
from functools import lru_cache

import structlog
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.config import settings

logger = structlog.get_logger(__name__)

# Derive a 32-byte Fernet key from the configured encryption key using PBKDF2.
# The salt is fixed per deployment — changing it would invalidate all encrypted data.
_SALT = b"bodhiorchard-secret-encryption-v1"


@lru_cache(maxsize=8)
def _derive(secret: str) -> Fernet:
    """A Fernet for one configured key (PBKDF2 is slow, so cached)."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=480_000,
    )
    return Fernet(base64.urlsafe_b64encode(kdf.derive(secret.encode())))


def _previous_keys() -> list[str]:
    raw = settings.auth.encryption_key_previous
    return [key.strip() for key in raw.split(",") if key.strip()]


def _get_fernet() -> MultiFernet:
    """Encrypt with ENCRYPTION_KEY; decrypt with it or any previous key."""
    keys = [settings.auth.encryption_key, *_previous_keys()]
    return MultiFernet([_derive(key) for key in keys])


def reencrypt_secret(stored: str) -> str | None:
    """``stored`` under the current key, or None if it already is (or isn't encrypted).

    Raises ``InvalidToken`` when no configured key can read it.
    """
    if not stored.startswith("enc:"):
        return None
    token = stored[4:].encode()
    try:
        _derive(settings.auth.encryption_key).decrypt(token)
        return None
    except InvalidToken:
        pass
    return f"enc:{_get_fernet().rotate(token).decode()}"


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a plaintext secret for database storage.

    Args:
        plaintext: The secret value to encrypt.

    Returns:
        Base64-encoded ciphertext string prefixed with 'enc:'.
    """
    if not plaintext:
        return ""
    ct = _get_fernet().encrypt(plaintext.encode())
    return f"enc:{ct.decode()}"


def decrypt_secret(stored: str) -> str:
    """Decrypt a secret retrieved from the database.

    Handles both encrypted (prefixed with 'enc:') and legacy plaintext values.
    Legacy plaintext values are returned as-is for backward compatibility
    until re-encrypted by the migration or next save.

    Args:
        stored: The stored value (encrypted or legacy plaintext).

    Returns:
        The decrypted plaintext secret.
    """
    if not stored:
        return ""
    if not stored.startswith("enc:"):
        # Legacy plaintext — return as-is
        return stored
    try:
        ct = stored[4:].encode()
        return _get_fernet().decrypt(ct).decode()
    except InvalidToken:
        logger.error(
            "decrypt_secret_failed",
            stored_prefix=stored[:20] + "..." if len(stored) > 20 else stored,
            hint="InvalidToken — ENCRYPTION_KEY may have changed or data is corrupted",
        )
        return ""
