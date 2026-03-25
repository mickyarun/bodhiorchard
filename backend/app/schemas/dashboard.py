"""Pydantic schemas for the Living Tree Dashboard API."""

from pydantic import BaseModel, Field


class LeafData(BaseModel):
    """A single leaf representing a commit."""

    path: str
    age_days: int
    color: str = Field(description="freshGreen | mediumGreen | deepGreen | wilted")
    branch_name: str
    has_bug: bool = False


class BranchData(BaseModel):
    """A branch representing a code community/module."""

    name: str
    file_count: int
    commit_count: int
    health: str = Field(description="thriving | healthy | dormant | wilted")
    bug_count: int = 0
    leaves: list[LeafData] = []


class BUDStageCount(BaseModel):
    """Count of BUDs at each lifecycle stage."""

    bud: int = 0
    design: int = 0
    development: int = 0
    testing: int = 0
    uat: int = 0
    prod: int = 0
    closed: int = 0
    discarded: int = 0


class MemberActivity(BaseModel):
    """A team member's activity summary for the tree."""

    user_id: str
    name: str
    email: str
    avatar_url: str | None = None
    care_pct: float = Field(description="0-100, percentage of recent commits by this member")
    top_modules: list[str] = []
    character_model: str | None = None
    presence: str = Field(default="active", description="active | on_break | at_home")


class SecurityThreat(BaseModel):
    """A bug/security issue shown as a termite on the tree."""

    id: str
    title: str
    severity: str
    module: str | None = None
    branch_name: str | None = None


class AgentActivityItem(BaseModel):
    """An AI agent's recent activity."""

    agent_name: str
    action: str
    timestamp: str
    status: str


class FeatureItem(BaseModel):
    """An individual feature from the feature registry."""

    title: str
    status: str = Field(description="planned | in_progress | implemented")
    source_ref: str | None = None
    branch_name: str | None = None
    repo_name: str | None = None
    from_bud: int | None = None
    linked_repos: list[str] = Field(default_factory=list)
    code_locations: dict[str, list[str]] | None = None
    repo_code_locations: dict[str, dict[str, list[str]]] | None = None


class BUDItem(BaseModel):
    """An individual BUD document summary."""

    bud_number: int
    title: str
    status: str = Field(description="lifecycle stage")
    branch_name: str | None = None
    repo_name: str | None = None


class FeatureSkillSummary(BaseModel):
    """Developer skill summary for a feature (bus factor analysis)."""

    feature_title: str
    developer_count: int = 0
    developers: list[str] = Field(
        default_factory=list,
        description="user_id list of developers skilled in this feature's modules",
    )
    top_developer_name: str | None = None


class RelationshipArc(BaseModel):
    """A code relationship arc between two branches/modules."""

    source_branch: str
    target_branch: str
    source_repo: str
    target_repo: str
    rel_type: str = Field(description="CALLS | IMPORTS | EXTENDS")
    weight: int


class RepoLimbData(BaseModel):
    """A major limb representing a tracked repository."""

    repo_name: str
    repo_path: str
    branches: list[BranchData] = []
    total_files: int = 0
    total_commits: int = 0
    health: str = Field(default="healthy", description="thriving | healthy | dormant | wilted")
    growth_stage: str = Field(default="medium", description="sprout | sapling | medium | mature")


class TreeData(BaseModel):
    """Complete data payload for the Living Tree visualization."""

    # Soil / roots
    symbol_count: int = 0
    relationship_count: int = 0

    # Trunk
    total_files: int = 0
    total_lines: int = 0
    project_age_days: int = 0

    # Repos (limbs) — primary structure
    repos: list[RepoLimbData] = []

    # Branches (backward compat: union of all repo branches)
    branches: list[BranchData] = []

    # BUD stages (flowers/fruit)
    bud_stages: BUDStageCount = Field(default_factory=BUDStageCount)
    total_features: int = 0
    features: list[FeatureItem] = []
    buds: list[BUDItem] = []

    # Members
    members: list[MemberActivity] = []

    # Security threats (termites)
    threats: list[SecurityThreat] = []

    # Agent activity (birds/bees)
    agent_activity: list[AgentActivityItem] = []

    # Code relationship arcs between branches
    relationships: list[RelationshipArc] = []

    # Feature skill summaries (bus factor analysis)
    feature_skills: list[FeatureSkillSummary] = []
