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

"""SQLAlchemy ORM models for Bodhiorchard.

All models are imported here so that Alembic can discover them for
auto-generation of migration scripts.
"""

from app.models.agent_activity import AgentActivityLog
from app.models.agent_skill import AgentSkill, AgentType
from app.models.agent_skill_bud_stage import AgentSkillBudStage
from app.models.backend_route_cache import BackendRouteCache
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
from app.models.bud_feature_link import (
    BUDFeatureLink,
    BUDFeatureLinkSource,
    BUDFeatureLinkType,
)
from app.models.bud_section_session import BUDSectionSession
from app.models.bud_stage_skill_override import BUDStageSkillOverride
from app.models.bud_todo import BUDTodo, BUDTodoStatus
from app.models.bud_version import MAX_VERSIONS_PER_PHASE, BUDEditSource, BUDVersion
from app.models.bug import Bug, BugSeverity, BugStatus
from app.models.cluster_cache import ClusterCache
from app.models.design_system import DesignSystemRef
from app.models.dev_activity import DevActivityLog
from app.models.developer_xp import DeveloperXP, RewardEvent, RewardType
from app.models.enterprise_rule import EnterpriseRule
from app.models.feature import Feature
from app.models.feature_learning import FeatureLearning
from app.models.feature_match_log import FeatureMatchLog
from app.models.feature_to_repo import FeatureToRepo, FeatureToRepoRole
from app.models.jira_import import ImportStatus, JiraImportSession, JiraIssueBudMap, MapStatus
from app.models.jwt_token import JWTToken
from app.models.mcp_audit_log import MCPAuditLogEntry
from app.models.notification import Notification, NotificationType
from app.models.organization import Organization
from app.models.permission import Permission, PermissionCategory
from app.models.pull_request import PRReviewStatus, PRState, PullRequest
from app.models.qa_test_evidence import QATestEvidence
from app.models.race_result import RaceResult
from app.models.repo_graph_cache import RepoGraphCache
from app.models.repo_layer import RepoLayer
from app.models.role import Role, RolePermission, RoleScopeType
from app.models.scan import ACTIVE_SCAN_STATUSES, Scan, ScanAggregateStatus
from app.models.scan_phase import (
    PHASE_SCOPE,
    SHA_REUSABLE_PHASES,
    TERMINAL_CHECKPOINT_STATUSES,
    CheckpointStatus,
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
from app.models.tracked_repository import RepoStatus, TrackedRepository
from app.models.triage_session import TriageSession, TriageStatus
from app.models.user import OrgToUser, User, UserEmailAlias, UserRole
from app.models.user_mcp_token import UserMCPToken
from app.models.webhook_log import WebhookLog

__all__ = [
    "AgentActivityLog",
    "AgentSkill",
    "AgentSkillBudStage",
    "AgentTaskStatus",
    "AgentType",
    "BackendRouteCache",
    "BUDAgentTask",
    "Base",
    "BaseModel",
    "BUDChatMessage",
    "BUDDesign",
    "BUDDesignStatus",
    "BUDDocument",
    "BUDEstimateSnapshot",
    "BUDFeatureLink",
    "BUDFeatureLinkSource",
    "BUDFeatureLinkType",
    "BUDSectionSession",
    "BUDStageSkillOverride",
    "BUDTodo",
    "BUDTodoStatus",
    "BUDEditSource",
    "BUDVersion",
    "MAX_VERSIONS_PER_PHASE",
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
    "FeatureMatchLog",
    "RepoGraphCache",
    "RepoRunStatus",
    "ScanKind",
    "StepStatus",
    "ImportStatus",
    "JiraImportSession",
    "JiraIssueBudMap",
    "JWTToken",
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
    "PhaseScope",
    "CheckpointStatus",
    "PHASE_SCOPE",
    "SHA_REUSABLE_PHASES",
    "TERMINAL_CHECKPOINT_STATUSES",
    "is_per_repo",
    "SkillProfile",
    "StandupReport",
    "Feature",
    "FeatureToRepo",
    "FeatureToRepoRole",
    "RepoLayer",
    "TrackedRepository",
    "TriageSession",
    "TriageStatus",
    "User",
    "UserEmailAlias",
    "UserMCPToken",
    "MCPAuditLogEntry",
    "UserRole",
    "WebhookLog",
    "RewardEvent",
    "RewardType",
]
