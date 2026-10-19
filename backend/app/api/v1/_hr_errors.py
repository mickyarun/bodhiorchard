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

"""Map HR encryption failures to 503, without leaking anything about them."""

import structlog
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.core.hr_crypto import HRCryptoUnavailableError, HRDecryptionError

logger = structlog.get_logger(__name__)

UNAVAILABLE = (
    "Sensitive details aren't available: the HR encryption key isn't configured. "
    "Ask your administrator to set HR_ENCRYPTION_KEYS."
)
UNREADABLE = "This can't be decrypted with the configured HR key. Ask your administrator."


async def _respond(request: Request, exc: Exception) -> JSONResponse:
    unavailable = isinstance(exc, HRCryptoUnavailableError)
    logger.error("hr_crypto_failed", path=request.url.path, kind=type(exc).__name__)
    return JSONResponse(
        {"detail": UNAVAILABLE if unavailable else UNREADABLE},
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def register_hr_errors(app: FastAPI) -> None:
    """Install the handlers; call wherever the API router is mounted."""
    app.add_exception_handler(HRCryptoUnavailableError, _respond)
    app.add_exception_handler(HRDecryptionError, _respond)
