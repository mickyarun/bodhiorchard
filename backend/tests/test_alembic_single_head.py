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

"""The migration history must have exactly one head.

Two branches that each add a migration on the same parent merge without a
textual conflict, so GitHub shows them as mergeable — and afterwards
``alembic upgrade head`` aborts with "Multiple head revisions", which also
stops the backend booting (``entrypoint.sh`` migrates on start). This test
turns that silent fork into a failing check on whichever PR lands second.
"""

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

BACKEND = Path(__file__).resolve().parents[1]


def test_migrations_have_a_single_head() -> None:
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    heads = ScriptDirectory.from_config(config).get_heads()
    assert len(heads) == 1, (
        f"alembic has {len(heads)} heads {sorted(heads)}: re-point the newest "
        "migration's down_revision at the current head (or add a merge revision)."
    )
