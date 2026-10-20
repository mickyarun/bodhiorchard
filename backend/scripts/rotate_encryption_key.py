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

"""Generate an ENCRYPTION_KEY, or re-encrypt stored secrets under the current one.

Usage (from backend/):
    python -m scripts.rotate_encryption_key --generate
        Print a new random key.
    python -m scripts.rotate_encryption_key --rotate [--dry-run]
        With ENCRYPTION_KEY set to the new key and ENCRYPTION_KEY_PREVIOUS
        to the old one, re-encrypt every stored secret still under the old
        key. Once it reports nothing left, drop ENCRYPTION_KEY_PREVIOUS.

Full Docker does this by itself on first start (see entrypoint.sh).
Exits non-zero when a secret can't be read with any configured key.
"""

import argparse
import asyncio
import secrets
import sys

from app.database import AsyncSessionLocal
from app.services.secret_rotation import rotate


async def _rotate(dry_run: bool) -> int:
    async with AsyncSessionLocal() as db:
        report = await rotate(db, dry_run=dry_run)
    verb = "Would re-encrypt" if dry_run else "Re-encrypted"
    print(f"{verb} {report.rotated} secrets.")
    for where in report.failed:
        print(f"  could not read {where} with any configured key")
    if report.failed:
        print("Keep the old key in ENCRYPTION_KEY_PREVIOUS until these are fixed.")
        return 1
    return 0


def main() -> None:
    """Parse arguments and run."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate", action="store_true", help="print a new key")
    group.add_argument("--rotate", action="store_true", help="re-encrypt under the current key")
    parser.add_argument("--dry-run", action="store_true", help="count without changing anything")
    args = parser.parse_args()
    if args.generate:
        print(secrets.token_urlsafe(48))
        return
    sys.exit(asyncio.run(_rotate(args.dry_run)))


if __name__ == "__main__":
    main()
