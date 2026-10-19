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

"""HR encryption, document checks and ID formats."""

import base64

import pytest
from pydantic import ValidationError

from app.core import hr_crypto
from app.schemas.employee_sensitive import SensitiveWrite
from app.services.employees.document_policy import check_document
from app.services.upload_policy import UploadPolicyError

KEY_A = base64.b64encode(b"a" * 32).decode()
KEY_B = base64.b64encode(b"b" * 32).decode()
RING = hr_crypto.parse_keyring(f"new:{KEY_B},old:{KEY_A}")
OLD_ONLY = hr_crypto.parse_keyring(f"old:{KEY_A}")


def test_round_trip_and_key_id() -> None:
    blob = hr_crypto.encrypt(b"ABCDE1234F", "org|profile|pan", RING)
    assert b"ABCDE1234F" not in blob
    assert hr_crypto.key_id(blob) == "new"
    assert hr_crypto.decrypt(blob, "org|profile|pan", RING) == b"ABCDE1234F"


def test_ciphertext_moved_to_another_row_fails() -> None:
    blob = hr_crypto.encrypt(b"secret", "org|alice|pan", RING)
    with pytest.raises(hr_crypto.HRDecryptionError):
        hr_crypto.decrypt(blob, "org|bob|pan", RING)


def test_tampering_and_unknown_keys_fail() -> None:
    blob = bytearray(hr_crypto.encrypt(b"secret", "aad", RING))
    blob[-1] ^= 1
    with pytest.raises(hr_crypto.HRDecryptionError):
        hr_crypto.decrypt(bytes(blob), "aad", RING)
    newer = hr_crypto.encrypt(b"secret", "aad", RING)
    with pytest.raises(hr_crypto.HRDecryptionError, match="No HR key"):
        hr_crypto.decrypt(newer, "aad", OLD_ONLY)


def test_truncated_blobs_fail_cleanly() -> None:
    blob = hr_crypto.encrypt(b"secret", "aad", RING)
    for cut in (blob[:1], blob[:5], blob[:20]):
        with pytest.raises(hr_crypto.HRDecryptionError):
            hr_crypto.decrypt(cut, "aad", RING)


def test_old_keys_still_decrypt_after_a_new_one_is_added() -> None:
    old = hr_crypto.encrypt(b"secret", "aad", OLD_ONLY)
    assert hr_crypto.decrypt(old, "aad", RING) == b"secret"


@pytest.mark.parametrize(
    "raw",
    ["nokid", "k1:" + base64.b64encode(b"short").decode(), f"k1:{KEY_A},k1:{KEY_B}"],
)
def test_malformed_keyrings_are_refused(raw: str) -> None:
    with pytest.raises(ValueError):
        hr_crypto.parse_keyring(raw)


def test_missing_keyring_is_unavailable() -> None:
    with pytest.raises(hr_crypto.HRCryptoUnavailableError):
        hr_crypto.parse_keyring(" ")


PDF = b"%PDF-1.7\n1 0 obj << /Type /Catalog >> endobj\n%%EOF"


def test_document_checks() -> None:
    assert check_document("offer.pdf", PDF) == "application/pdf"
    assert check_document("photo.JPG", b"\xff\xd8\xff\xe0rest") == "image/jpeg"
    with pytest.raises(UploadPolicyError, match="isn't really"):
        check_document("invoice.pdf", b"MZ\x90\x00 windows exe")
    with pytest.raises(UploadPolicyError, match="scripts"):
        check_document("form.pdf", PDF + b" /OpenAction << /S /JavaScript /JS (app.alert(1)) >>")
    with pytest.raises(UploadPolicyError, match="scripts"):
        check_document("escaped.pdf", PDF + b" << /S /J#61vaScript >>")
    with pytest.raises(UploadPolicyError):
        check_document("letter.docx", b"PK\x03\x04")
    with pytest.raises(UploadPolicyError):
        check_document("big.pdf", b"%PDF-" + b"0" * (10 * 1024 * 1024))


def test_id_formats_are_checked_and_normalised() -> None:
    body = SensitiveWrite(pan="abcde 1234 f", aadhaar="1234 5678 9012", bank_ifsc="hdfc0001234")
    assert (body.pan, body.aadhaar, body.bank_ifsc) == (
        "ABCDE1234F",
        "123456789012",
        "HDFC0001234",
    )
    for bad in ({"pan": "12345"}, {"aadhaar": "1234"}, {"bank_account_number": "abc"}):
        with pytest.raises(ValidationError):
            SensitiveWrite.model_validate(bad)
    assert SensitiveWrite(pan="").pan == ""  # clearing a value
