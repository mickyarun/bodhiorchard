# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

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
