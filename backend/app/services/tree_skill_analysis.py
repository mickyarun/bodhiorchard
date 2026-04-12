"""Feature-skill (bus factor) analysis for the Living Tree Dashboard.

Matches developers to features by module name and computes per-feature
skill summaries. Depends on ``tree.features`` being fully populated
before being called.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.skill_profile import SkillProfile
from app.models.user import User
from app.schemas.dashboard import FeatureSkillSummary, TreeData


async def compute_feature_skills(
    db: AsyncSession,
    org_id: uuid.UUID,
    tree: TreeData,
) -> None:
    """Compute developer skill summaries per feature for bus-factor analysis.

    Matches developers to features by module name. For each feature, finds
    developers whose ``SkillProfile.module`` matches the feature's
    ``branch_name`` (case-insensitive substring). This works because
    branch names are top-level directory communities and skill modules
    are the same directories.

    Falls back to ``feature_id`` FK when available, but most profiles
    use module matching.

    Args:
        db: Async database session.
        org_id: Organization UUID.
        tree: The tree data; ``tree.features`` must be populated first.
    """
    # 1. Load all skill profiles for this org (module → developers)
    result = await db.execute(
        select(
            SkillProfile.module,
            SkillProfile.user_id,
            SkillProfile.skill_score,
            SkillProfile.feature_id,
            User.name.label("dev_name"),
        )
        .join(User, User.id == SkillProfile.user_id)
        .where(SkillProfile.org_id == org_id)
        .where(SkillProfile.skill_score > 0.1)
        .where(User.is_active.is_(True))
        .order_by(SkillProfile.skill_score.desc())
    )
    rows = result.all()

    # Build module→developers lookup: module_lower → [(uid, name, score)]
    module_devs: dict[str, list[tuple[str, str, float]]] = {}
    for module, user_id, score, _feature_id, dev_name in rows:
        key = module.lower()
        module_devs.setdefault(key, []).append((str(user_id), dev_name, float(score)))

    # 2. For each unique feature title, find matching developers
    seen_titles: set[str] = set()
    for feat in tree.features:
        if feat.title in seen_titles:
            continue
        seen_titles.add(feat.title)

        matched: dict[str, tuple[str, float]] = {}  # uid → (name, best_score)

        # Extract keywords from feature title for matching
        raw_title = feat.title.lower()
        if raw_title.startswith("feature:"):
            raw_title = raw_title[8:]
        title_words = [
            w for w in raw_title.split()
            if len(w) > 2 and w not in {"the", "and", "for", "with"}
        ]

        # Match by branch_name (module == branch/community name)
        if feat.branch_name:
            branch_lower = feat.branch_name.lower()
            for mod_key, devs in module_devs.items():
                if branch_lower in mod_key or mod_key in branch_lower:
                    for uid, name, score in devs:
                        if uid not in matched or score > matched[uid][1]:
                            matched[uid] = (name, score)

        # Match by title keywords against module names (2+ keyword hits)
        if not matched and len(title_words) >= 2:
            for mod_key, devs in module_devs.items():
                hits = sum(1 for w in title_words if w in mod_key)
                if hits >= 2:
                    for uid, name, score in devs:
                        if uid not in matched or score > matched[uid][1]:
                            matched[uid] = (name, score)

        if not matched:
            continue

        sorted_devs = sorted(matched.items(), key=lambda x: x[1][1], reverse=True)

        tree.feature_skills.append(
            FeatureSkillSummary(
                feature_title=feat.title,
                developer_count=len(sorted_devs),
                developers=[uid for uid, _ in sorted_devs],
                top_developer_name=sorted_devs[0][1][0] if sorted_devs else None,
            )
        )
