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

"""Encryption for employees' sensitive details and documents (AES-256-GCM).

Blob format: ``kid length (1 byte) | kid | 12-byte nonce | ciphertext+tag``.
The associated data binds each blob to where it belongs (org, profile,
field or document), so ciphertext copied from one row to another fails
to decrypt instead of quietly showing someone else's data.

This protects database dumps, backups and object storage. Anyone with
the host's environment can still read the key; access control and the
audit trail are the barrier there.
"""

import base64
import os
from dataclasses import dataclass
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

NONCE_BYTES = 12
TAG_BYTES = 16
KEY_BYTES = 32


class HRCryptoUnavailableError(RuntimeError):
    """No HR key is configured, so sensitive data can't be stored or read."""


class HRDecryptionError(RuntimeError):
    """A blob couldn't be decrypted: wrong key, unknown kid, or tampered data."""


@dataclass(frozen=True)
class Keyring:
    """Keys by id; ``current`` encrypts new data."""

    current: str
    keys: dict[str, bytes]


def parse_keyring(raw: str) -> Keyring:
    """Parse ``kid:base64key,kid:base64key`` (newest first); ValueError if malformed."""
    keys: dict[str, bytes] = {}
    order: list[str] = []
    for entry in (part.strip() for part in raw.split(",")):
        if not entry:
            continue
        kid, sep, encoded = entry.partition(":")
        if not sep or not kid or len(kid.encode()) > 255:
            raise ValueError("Each HR key must look like kid:base64key.")
        key = base64.b64decode(encoded, validate=True)
        if len(key) != KEY_BYTES:
            raise ValueError(f"HR key {kid!r} must be {KEY_BYTES} bytes.")
        if kid in keys:
            raise ValueError(f"HR key id {kid!r} appears twice.")
        keys[kid] = key
        order.append(kid)
    if not order:
        raise HRCryptoUnavailableError("HR_ENCRYPTION_KEYS is not set.")
    return Keyring(current=order[0], keys=keys)


@lru_cache(maxsize=1)
def _configured_keyring(raw: str) -> Keyring:
    return parse_keyring(raw)


def keyring() -> Keyring:
    """The configured keyring; HRCryptoUnavailableError if missing or malformed."""
    try:
        return _configured_keyring(settings.hr_crypto.hr_encryption_keys.get_secret_value())
    except ValueError as exc:
        # Never echo the value: it is the key.
        raise HRCryptoUnavailableError("HR_ENCRYPTION_KEYS is malformed.") from exc


def generate_key() -> str:
    """A new random key, base64-encoded, for a keyring entry."""
    return base64.b64encode(os.urandom(KEY_BYTES)).decode()


def encrypt(plaintext: bytes, aad: str, ring: Keyring | None = None) -> bytes:
    """Encrypt with the current key, bound to ``aad``."""
    ring = ring or keyring()
    kid = ring.current.encode()
    nonce = os.urandom(NONCE_BYTES)
    sealed = AESGCM(ring.keys[ring.current]).encrypt(nonce, plaintext, aad.encode())
    return bytes([len(kid)]) + kid + nonce + sealed


def decrypt(blob: bytes, aad: str, ring: Keyring | None = None) -> bytes:
    """Decrypt a blob made by :func:`encrypt` for the same ``aad``."""
    ring = ring or keyring()
    kid_len = blob[0] if blob else 0
    if len(blob) < 1 + kid_len + NONCE_BYTES + TAG_BYTES:
        raise HRDecryptionError("Blob is too short.")
    kid = blob[1 : 1 + kid_len].decode(errors="replace")
    key = ring.keys.get(kid)
    if key is None:
        raise HRDecryptionError(f"No HR key with id {kid!r}.")
    start = 1 + kid_len
    nonce, sealed = blob[start : start + NONCE_BYTES], blob[start + NONCE_BYTES :]
    try:
        return AESGCM(key).decrypt(nonce, sealed, aad.encode())
    except InvalidTag as exc:
        raise HRDecryptionError("Blob failed its integrity check.") from exc


def key_id(blob: bytes) -> str:
    """The id of the key a blob was encrypted with (for rotation)."""
    return blob[1 : 1 + blob[0]].decode(errors="replace") if blob else ""
