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

"""A CSV download response for people data.

Returning a ``Response`` skips the router's ``no_store`` dependency (FastAPI
only merges headers into responses it builds), so this sets them itself.
"""

from fastapi import Response

CSV_TYPE = "text/csv; charset=utf-8"


def csv_response(content: bytes, filename: str) -> Response:
    """``content`` as an attachment named ``filename`` (ASCII), never cached."""
    return Response(
        content=content,
        media_type=CSV_TYPE,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store, private",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )
