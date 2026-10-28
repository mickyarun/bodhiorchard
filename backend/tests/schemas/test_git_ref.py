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

"""Branch names follow ``git check-ref-format --branch`` in every schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.git_ref import branch_name_problem
from app.schemas.repo_install import BulkOnboardItem
from app.schemas.settings import RepoBranchUpdate
from app.schemas.setup import SetupRepo

GOOD = [
    "main",
    "master",
    "develop",
    "release/uat",
    "feature/BUD-123-fix",
    "v1.2.3",
    "a.b",
    "user@host",
    "x" * 100,
    "deps/upgrade-node_20",
    "release/2026.10",
]

BAD = [
    "",
    ".",
    "..",
    "@",
    "-main",
    "--upload-pack=x",
    "a..b",
    "../escape",
    "/main",
    "main/",
    "a//b",
    ".hidden",
    "release/.hidden",
    "main.lock",
    "release/main.lock/x",
    "main.",
    "a@{1}",
    "has space",
    "tab\there",
    "new\nline",
    "nul\x00",
    "del\x7f",
    "tilde~1",
    "caret^",
    "colon:x",
    "what?",
    "star*",
    "bracket[",
    "back\\slash",
]


@pytest.mark.parametrize("name", GOOD)
def test_good_names_pass(name: str) -> None:
    assert branch_name_problem(name) is None


@pytest.mark.parametrize("name", BAD)
def test_bad_names_are_refused(name: str) -> None:
    assert branch_name_problem(name) is not None


@pytest.mark.parametrize("name", BAD + ["x" * 101])
def test_every_schema_refuses_a_bad_name(name: str) -> None:
    with pytest.raises(ValidationError):
        RepoBranchUpdate.model_validate({"mainBranch": name})
    with pytest.raises(ValidationError):
        RepoBranchUpdate.model_validate({"developBranch": name})
    with pytest.raises(ValidationError):
        BulkOnboardItem.model_validate({"fullName": "acme/widgets", "mainBranch": name})
    with pytest.raises(ValidationError):
        BulkOnboardItem.model_validate(
            {"fullName": "acme/widgets", "mainBranch": "main", "developBranch": name}
        )
    with pytest.raises(ValidationError):
        SetupRepo.model_validate({"path": "/repo", "mainBranch": name})
    with pytest.raises(ValidationError):
        SetupRepo.model_validate({"path": "/repo", "developBranch": name})


@pytest.mark.parametrize("name", [n for n in BAD if n])
def test_uat_refuses_a_bad_name_but_empty_still_clears(name: str) -> None:
    with pytest.raises(ValidationError):
        RepoBranchUpdate.model_validate({"uatBranch": name})
    with pytest.raises(ValidationError):
        BulkOnboardItem.model_validate(
            {"fullName": "acme/widgets", "mainBranch": "main", "uatBranch": name}
        )
    assert RepoBranchUpdate.model_validate({"uatBranch": ""}).uat_branch == ""


def test_good_names_and_omitted_optionals_still_validate() -> None:
    update = RepoBranchUpdate.model_validate(
        {"mainBranch": "main", "developBranch": "develop", "uatBranch": "release/uat"}
    )
    assert (update.main_branch, update.develop_branch, update.uat_branch) == (
        "main",
        "develop",
        "release/uat",
    )
    assert RepoBranchUpdate.model_validate({}).main_branch is None
    item = BulkOnboardItem.model_validate({"fullName": "acme/widgets", "mainBranch": "main"})
    assert item.develop_branch is None
    assert SetupRepo.model_validate({"path": "/repo"}).main_branch is None
