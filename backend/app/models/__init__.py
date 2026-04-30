# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""SQLAlchemy ORM models for Bodhiorchard.

All models are imported here so that Alembic can discover them for
auto-generation of migration scripts.
"""

from app.models.agent_activity import AgentActivityLog
from app.models.agent_skill import AgentSkill
from app.models.agent_skill_bud_stage import AgentSkillBudStage
from app.models.base import Base, BaseModel
from app.models.bud import (
    BUDChatMessage,
    BUDDesign,
    BUDDesignStatus,
    BUDDocument,
    BUDStatus,
    BUDTimelineEvent,
    BUDTimelineEventType,
)
from app.models.bud_agent_task import AgentTaskStatus, BUDAgentTask
from app.models.bud_estimate_snapshot import BUDEstimateSnapshot
from app.models.bud_todo import BUDTodo, BUDTodoStatus
from app.models.bug import Bug, BugSeverity, BugStatus
from app.models.cluster_cache import ClusterCache
from app.models.design_system import DesignSystemRef
from app.models.dev_activity import DevActivityLog
from app.models.developer_xp import DeveloperXP, RewardEvent, RewardType
from app.models.enterprise_rule import EnterpriseRule
from app.models.feature_learning import FeatureLearning
from app.models.jira_import import ImportStatus, JiraImportSession, JiraIssueBudMap, MapStatus
from app.models.jwt_token import JWTToken
from app.models.knowledge_item import KnowledgeItem, KnowledgeRepoLink
from app.models.notification import Notification, NotificationType
from app.models.organization import Organization
from app.models.permission import (
    Permission,
    PermissionCategory,
    Role,
    RolePermission,
    RoleScopeType,
)
from app.models.pull_request import PRReviewStatus, PRState, PullRequest
from app.models.qa_test_evidence import QATestEvidence
from app.models.race_result import RaceResult
from app.models.repo_graph_cache import RepoGraphCache
from app.models.scan import ACTIVE_SCAN_STATUSES, Scan, ScanAggregateStatus
from app.models.scan_phase import (
    PHASE_SCOPE,
    SHA_REUSABLE_PHASES,
    TERMINAL_CHECKPOINT_STATUSES,
    CheckpointStatus,
    MergeOutcome,
    PhaseScope,
    ScanErrorCode,
    ScanPhase,
    is_per_repo,
)
from app.models.scan_phase_checkpoint import ScanPhaseCheckpoint
from app.models.scan_repo_run import ScanRepoRun
from app.models.scan_repo_step import ScanRepoStep
from app.models.scan_run_enums import (
    RepoRunStatus,
    ScanKind,
    StepStatus,
)
from app.models.skill_profile import SkillProfile
from app.models.standup import StandupReport
from app.models.synthesized_feature import SynthesizedFeature
from app.models.tracked_repository import RepoStatus, TrackedRepository
from app.models.triage_session import TriageSession, TriageStatus
from app.models.user import OrgToUser, User, UserEmailAlias, UserRole
from app.models.user_mcp_token import UserMCPToken

__all__ = [
    "AgentActivityLog",
    "AgentSkill",
    "AgentSkillBudStage",
    "AgentTaskStatus",
    "BUDAgentTask",
    "Base",
    "BaseModel",
    "BUDChatMessage",
    "BUDDesign",
    "BUDDesignStatus",
    "BUDDocument",
    "BUDEstimateSnapshot",
    "BUDTodo",
    "BUDTodoStatus",
    "BUDStatus",
    "BUDTimelineEvent",
    "BUDTimelineEventType",
    "Bug",
    "BugSeverity",
    "BugStatus",
    "ClusterCache",
    "DesignSystemRef",
    "DevActivityLog",
    "DeveloperXP",
    "EnterpriseRule",
    "FeatureLearning",
    "RepoGraphCache",
    "RepoRunStatus",
    "ScanKind",
    "StepStatus",
    "ImportStatus",
    "JiraImportSession",
    "JiraIssueBudMap",
    "JWTToken",
    "KnowledgeItem",
    "KnowledgeRepoLink",
    "MapStatus",
    "Notification",
    "NotificationType",
    "Organization",
    "OrgToUser",
    "Permission",
    "PermissionCategory",
    "PRReviewStatus",
    "PRState",
    "PullRequest",
    "QATestEvidence",
    "RaceResult",
    "RepoStatus",
    "Role",
    "RolePermission",
    "RoleScopeType",
    "Scan",
    "ScanAggregateStatus",
    "ACTIVE_SCAN_STATUSES",
    "ScanPhaseCheckpoint",
    "ScanRepoRun",
    "ScanRepoStep",
    "ScanPhase",
    "ScanErrorCode",
    "MergeOutcome",
    "PhaseScope",
    "CheckpointStatus",
    "PHASE_SCOPE",
    "SHA_REUSABLE_PHASES",
    "TERMINAL_CHECKPOINT_STATUSES",
    "is_per_repo",
    "SkillProfile",
    "StandupReport",
    "SynthesizedFeature",
    "TrackedRepository",
    "TriageSession",
    "TriageStatus",
    "User",
    "UserEmailAlias",
    "UserMCPToken",
    "UserRole",
    "RewardEvent",
    "RewardType",
]
