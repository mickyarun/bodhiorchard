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

"""What an employee document may be, checked on the plaintext before encryption.

Only PDF, JPEG and PNG. The extension picks the type, the file's first
bytes must match it (so a renamed executable or HTML page is refused), and
PDFs naming scripts or launch actions are refused. That last check is best
effort: it reads the raw file (with #xx-escaped names decoded), not
compressed object streams. Files are only ever served back as the type
their extension says, so a missed script still can't run in the app. Word files
are deliberately not accepted: they're the usual vehicle for macros.
"""

import re

from app.services.upload_policy import UploadPolicy, UploadPolicyError

MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
ENCRYPTION_OVERHEAD = 512

DOCUMENT_POLICY = UploadPolicy.for_extensions(
    label="Employee document",
    max_bytes=MAX_DOCUMENT_BYTES,
    extensions={
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
    },
)

# What reaches storage is ciphertext, so the storage-layer check can only
# look at size and the fixed content type; the real checks ran above.
ENCRYPTED_BLOB_POLICY = UploadPolicy(
    label="Encrypted employee document",
    max_bytes=MAX_DOCUMENT_BYTES + ENCRYPTION_OVERHEAD,
    mime_types=frozenset({"application/octet-stream"}),
)

_MAGIC = {
    "application/pdf": (b"%PDF-",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
}
_PDF_ACTIVE = re.compile(rb"/(JavaScript|JS|Launch)\b")
_PDF_NAME_ESCAPE = re.compile(rb"#([0-9A-Fa-f]{2})")


def check_document(filename: str, data: bytes) -> str:
    """The canonical MIME type for an acceptable file; UploadPolicyError otherwise."""
    DOCUMENT_POLICY.check_size(len(data))
    if not data:
        raise UploadPolicyError("That file is empty.")
    mime = DOCUMENT_POLICY.resolve_mime(filename)
    if not data.startswith(_MAGIC[mime]):
        raise UploadPolicyError("That file isn't really a PDF, JPEG or PNG.")
    if mime == "application/pdf" and _PDF_ACTIVE.search(_decode_names(data)):
        raise UploadPolicyError("PDFs with scripts or launch actions can't be uploaded.")
    return mime


def _decode_names(data: bytes) -> bytes:
    """Undo PDF name escapes, so ``/J#61vaScript`` reads as ``/JavaScript``."""
    return _PDF_NAME_ESCAPE.sub(lambda m: bytes([int(m.group(1), 16)]), data)
