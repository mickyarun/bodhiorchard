"""SQLAlchemy ORM models for Bodhigrove.

All models are imported here so that Alembic can discover them for
auto-generation of migration scripts.
"""

from app.models.agent_activity import AgentActivityLog
from app.models.agent_log import AgentLog
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
from app.models.bug import Bug, BugSeverity, BugStatus
from app.models.design_system import DesignSystemRef
from app.models.dev_activity import DevActivityLog
from app.models.developer_xp import DeveloperXP, XPEvent
from app.models.enterprise_rule import EnterpriseRule
from app.models.feature_learning import FeatureLearning
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
from app.models.skill_profile import SkillProfile
from app.models.standup import StandupReport
from app.models.tracked_repository import RepoStatus, TrackedRepository
from app.models.triage_session import TriageSession, TriageStatus
from app.models.user import OrgToUser, User, UserEmailAlias, UserRole
from app.models.user_mcp_token import UserMCPToken

__all__ = [
    "AgentActivityLog",
    "AgentLog",
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
    "BUDStatus",
    "BUDTimelineEvent",
    "BUDTimelineEventType",
    "Bug",
    "BugSeverity",
    "BugStatus",
    "DesignSystemRef",
    "DevActivityLog",
    "DeveloperXP",
    "EnterpriseRule",
    "FeatureLearning",
    "JWTToken",
    "KnowledgeItem",
    "KnowledgeRepoLink",
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
    "RepoStatus",
    "Role",
    "RolePermission",
    "RoleScopeType",
    "SkillProfile",
    "StandupReport",
    "TrackedRepository",
    "TriageSession",
    "TriageStatus",
    "User",
    "UserEmailAlias",
    "UserMCPToken",
    "UserRole",
    "XPEvent",
]
