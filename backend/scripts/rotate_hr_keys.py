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

"""Generate an HR encryption key, or re-encrypt HR data under the newest one.

Usage (from backend/):
    python -m scripts.rotate_hr_keys --generate
        Print a new keyring entry. Put it FIRST in HR_ENCRYPTION_KEYS and keep
        the old entries after it, e.g. HR_ENCRYPTION_KEYS="k2026b:...,k2026a:..."
    python -m scripts.rotate_hr_keys --rotate [--dry-run]
        Re-encrypt every sensitive field and document still under an older
        key. Once it reports nothing left, the old keys can be removed.
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime

from app.core.hr_crypto import generate_key
from app.database import AsyncSessionLocal
from app.services.employees.hr_key_rotation import rotate


async def _rotate(dry_run: bool) -> int:
    async with AsyncSessionLocal() as db:
        report = await rotate(db, dry_run=dry_run)
    verb = "Would re-encrypt" if dry_run else "Re-encrypted"
    print(f"{verb} {report.fields} fields and {report.documents} documents.")
    for item in report.failed:
        print(f"  could not re-encrypt {item}")
    if report.failed:
        print("Keep the old keys until these are fixed and a re-run reports none.")
        return 1
    return 0


def main() -> None:
    """Parse arguments and run."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--generate", action="store_true", help="print a new key entry")
    group.add_argument("--rotate", action="store_true", help="re-encrypt under the newest key")
    parser.add_argument("--dry-run", action="store_true", help="count without changing anything")
    args = parser.parse_args()
    if args.generate:
        print(f"k{datetime.now(UTC):%Y%m%d}:{generate_key()}")
        return
    # Non-zero when anything was skipped, so a script never drops the old key early.
    sys.exit(asyncio.run(_rotate(args.dry_run)))


if __name__ == "__main__":
    main()
