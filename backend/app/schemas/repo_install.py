# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Schemas for the bulk GitHub-App repo import flow.

Used by the ``GET /v1/settings/repos/installable`` and bulk-onboard
endpoints. Field names are snake_case in Python with camelCase aliases
so the Vue frontend can consume the JSON unchanged.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class InstallableRepo(BaseModel):
    """One entry in the installation's repository list.

    ``already_tracked`` is computed on the backend by joining against
    ``TrackedRepository.github_repo_full_name`` for the org so the
    picker can grey out repos that are already onboarded.
    """

    full_name: str = Field(alias="fullName")
    owner_login: str = Field(alias="ownerLogin")
    owner_avatar_url: str = Field(alias="ownerAvatarUrl")
    default_branch: str = Field(alias="defaultBranch")
    private: bool
    gh_repo_id: int = Field(alias="ghRepoId")
    already_tracked: bool = Field(alias="alreadyTracked")
    pushed_at: datetime | None = Field(default=None, alias="pushedAt")

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class AppInstallState(StrEnum):
    """Tri-state describing whether the picker can render its list.

    Mirrors :class:`app.schemas.settings.GitHubAppStatus` but expressed
    from the picker's point of view (which doesn't care about the
    distinction between "no app id" and "no private key" — both are
    ``NO_CREDENTIALS``).
    """

    READY = "ready"
    NO_CREDENTIALS = "no_credentials"
    NO_INSTALL = "no_install"


class InstallableListResponse(BaseModel):
    """Response body for ``GET /v1/settings/repos/installable``."""

    app_install_state: AppInstallState = Field(alias="appInstallState")
    install_url: str | None = Field(default=None, alias="installUrl")
    repos: list[InstallableRepo]

    model_config = ConfigDict(populate_by_name=True)


class RepoBranchList(BaseModel):
    """Response body for the per-repo branch list endpoint.

    Distinct from ``app.schemas.settings.RepoBranchList`` (which carries
    the currently-selected main/develop/uat for a tracked repo); this
    one is for repos that aren't tracked yet so it only carries names.
    """

    branches: list[str]


class BulkOnboardItem(BaseModel):
    """One row in a bulk-onboard request — Phase C consumes these."""

    full_name: str = Field(alias="fullName")
    main_branch: str = Field(alias="mainBranch")
    develop_branch: str | None = Field(default=None, alias="developBranch")
    uat_branch: str | None = Field(default=None, alias="uatBranch")

    model_config = ConfigDict(populate_by_name=True)


class BulkOnboardRequest(BaseModel):
    """Bulk-onboard request body — Phase C consumes this."""

    items: list[BulkOnboardItem] = Field(min_length=1, max_length=200)
