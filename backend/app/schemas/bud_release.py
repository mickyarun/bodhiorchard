"""Pydantic schemas for the BUD release-stage detail endpoint.

Drives the UAT and Prod tabs on the BUD detail page. A single schema
serves both stages — the ``stage`` field discriminates. The shape mirrors
what ``release_detection.detect_release_promotion`` writes into each
``merged_to_uat`` / ``merged_to_prod`` timeline event's ``detail`` JSON,
plus a top-level status derived from the presence and timestamps of
those events.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ReleaseStage = Literal["uat", "prod"]
ReleaseStageStatus = Literal["not_reached", "in_stage", "passed"]


class ReleasePR(BaseModel):
    """A release PR (e.g. develop \u2192 release/uat) that promoted this BUD.

    One per impacted repo per promotion event. Sourced from the timeline
    event detail JSON written by ``detect_release_promotion``.
    """

    pr_number: int = Field(alias="prNumber")
    repo_name: str = Field(alias="repoName")
    html_url: str = Field(alias="htmlUrl")
    title: str | None = None
    author_login: str | None = Field(None, alias="authorLogin")
    merged_at: datetime | None = Field(None, alias="mergedAt")

    model_config = {"populate_by_name": True}


class ReleaseCommit(BaseModel):
    """A BUD-owned commit that appeared in the release PR.

    Lets the UI show 'these N commits from this BUD shipped in that
    release', so devs can spot dropped or cherry-picked work.
    """

    sha: str
    short_sha: str = Field(alias="shortSha")
    message: str | None = None
    repo_name: str = Field(alias="repoName")

    model_config = {"populate_by_name": True}


class ReleaseTimelineEvent(BaseModel):
    """A merged_to_{uat,prod} timeline event for this BUD."""

    occurred_at: datetime = Field(alias="occurredAt")
    pr_number: int = Field(alias="prNumber")
    repo_name: str = Field(alias="repoName")
    html_url: str = Field(alias="htmlUrl")

    model_config = {"populate_by_name": True}


class BUDReleaseStage(BaseModel):
    """Release-stage detail for a single BUD and stage.

    ``status`` is derived from event presence:
    - ``not_reached``: no merged_to_{stage} event for this BUD
    - ``in_stage``: at least one event for this stage, no event for the
      next stage (e.g. UAT events but no Prod events yet)
    - ``passed``: this BUD has events for the next stage as well
      (only meaningful for UAT; Prod is terminal and never reaches ``passed``)
    """

    bud_id: str = Field(alias="budId")
    stage: ReleaseStage
    status: ReleaseStageStatus
    first_reached_at: datetime | None = Field(None, alias="firstReachedAt")
    release_prs: list[ReleasePR] = Field(default_factory=list, alias="releasePRs")
    open_prs: list[ReleasePR] = Field(default_factory=list, alias="openPRs")
    commits: list[ReleaseCommit] = Field(default_factory=list)
    events: list[ReleaseTimelineEvent] = Field(default_factory=list)

    model_config = {"populate_by_name": True}
