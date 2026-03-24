"""SQLAlchemy ORM models for Bodhigrove.

All models are imported here so that Alembic can discover them for
auto-generation of migration scripts.
"""

from app.models.agent_log import AgentLog
from app.models.agent_skill_override import AgentSkillOverride
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
from app.models.bud_commit import BUDCommit
from app.models.bug import Bug, BugSeverity, BugStatus
from app.models.code_embedding import CodeEmbedding
from app.models.design_system import DesignSystemRef
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
from app.models.skill_profile import SkillProfile
from app.models.standup import StandupReport
from app.models.tracked_repository import RepoStatus, TrackedRepository
from app.models.triage_session import TriageSession, TriageStatus
from app.models.user import OrgToUser, User, UserEmailAlias, UserRole

__all__ = [
    "AgentLog",
    "AgentSkillOverride",
    "Base",
    "BaseModel",
    "BUDChatMessage",
    "BUDDesign",
    "BUDDesignStatus",
    "BUDDocument",
    "BUDStatus",
    "BUDTimelineEvent",
    "BUDTimelineEventType",
    "BUDCommit",
    "Bug",
    "BugSeverity",
    "BugStatus",
    "CodeEmbedding",
    "DesignSystemRef",
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
    "UserRole",
]
