"""Symmetric encryption for secrets stored in the database.

Uses Fernet (AES-128-CBC + HMAC-SHA256) with a key derived from the
ENCRYPTION_KEY environment variable via PBKDF2.
"""

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.config import settings

# Derive a 32-byte Fernet key from the configured encryption key using PBKDF2.
# The salt is fixed per deployment — changing it would invalidate all encrypted data.
_SALT = b"flowdev-secret-encryption-v1"


def _get_fernet() -> Fernet:
    """Build a Fernet instance from the configured encryption key."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=480_000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(settings.auth.encryption_key.encode()))
    return Fernet(key)


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
        return ""
