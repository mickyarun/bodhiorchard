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

"""One unreadable folder must not hide the rest of the listing.

Checking a child for ``.git`` stats a path inside it, which raises
``PermissionError`` when the child cannot be opened; so does ``is_dir`` on
a symlink into such a folder. Either used to escape the walk, and the
picker answered 403 for the whole parent — so a single locked folder in
the home directory made home unbrowsable.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.services.directory_listing import list_subdirectories

pytestmark = pytest.mark.skipif(os.geteuid() == 0, reason="root opens any folder")


@pytest.fixture
def home(tmp_path: Path) -> Iterator[Path]:
    """A repo, a plain folder, a locked folder and a link into the locked one."""
    root = tmp_path / "home"
    (root / "plain").mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(root / "repo")], check=True, capture_output=True)
    locked = root / "locked"
    (locked / "inner").mkdir(parents=True)
    (root / "shortcut").symlink_to(locked / "inner")
    locked.chmod(0)
    yield root
    locked.chmod(0o755)


def test_lists_siblings_of_an_unreadable_folder(home: Path) -> None:
    """The locked folder shows as not a repo; the link into it, which cannot be
    followed to tell whether it is a folder, is left out."""
    entries = {e.name: e.is_git_repo for e in list_subdirectories(home)}
    assert entries == {"locked": False, "plain": False, "repo": True}


def test_the_unreadable_folder_itself_still_refuses(home: Path) -> None:
    """Opening the locked folder is still an error; the endpoint maps it to 403."""
    with pytest.raises(PermissionError):
        list_subdirectories(home / "locked")
