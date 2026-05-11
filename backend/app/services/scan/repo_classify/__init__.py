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

"""Repo layer / tech-stack / db-flavor classifier.

Per-repo stage at :mod:`app.services.scan.stages.classify_repo` calls
:func:`classify` to populate ``tracked_repositories.repo_layer``,
``tech_stack``, and ``db_flavor`` after ingest. The functions in this
module are pure (no DB, no IO outside the supplied worktree path) so they
can be exercised under unit tests with synthetic worktrees.
"""

from app.services.scan.repo_classify.mode_detection import (
    Classification,
    classify,
    classify_from_name,
    classify_from_worktree,
)

__all__ = [
    "Classification",
    "classify",
    "classify_from_name",
    "classify_from_worktree",
]
