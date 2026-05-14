#!/usr/bin/env python3
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

"""Analyze scan pipeline results and dump diagnostic info.

Usage (from backend/):
    python -m scripts.scan_analyzer
    python -m scripts.scan_analyzer --output scan_debug.log

Checks:
    1. Features: count, repo links, code_locations, embeddings
    2. Skill profiles: feature_id coverage, language distribution
    3. Orphans: features without repo links
    4. Junction table: code_locations population
    5. Feature map: what load_feature_map would produce
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add backend/ to path so imports work
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def run_analysis(output_file: str | None = None) -> None:
    """Run all diagnostic checks and print/write results."""
    from app.models.knowledge_item import KnowledgeItem, KnowledgeRepoLink
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.skill_profile import SkillProfile
    from app.models.tracked_repository import TrackedRepository
    from app.models.user import User

    lines: list[str] = []

    def log(msg: str = "") -> None:
        lines.append(msg)
        print(msg)

    async with AsyncSessionLocal() as db:
        # Get first org
        from app.models.organization import Organization

        org_row = await db.execute(select(Organization).limit(1))
        org = org_row.scalar_one_or_none()
        if not org:
            log("ERROR: No organization found. Run setup wizard first.")
            return

        org_id = org.id
        log(f"=== Scan Analyzer for org: {org.name} ({org_id}) ===")
        log()

        # --- Tracked Repos ---
        repos_result = await db.execute(
            select(TrackedRepository).where(TrackedRepository.org_id == org_id)
        )
        repos = list(repos_result.scalars().all())
        log(f"--- Tracked Repositories ({len(repos)}) ---")
        for r in repos:
            log(
                f"  {r.name:30s}  status={r.status}  main={r.main_branch}  "
                f"head_sha={str(r.head_sha or '')[:8]}  path={r.path}"
            )
        log()

        # --- Features ---
        features_result = await db.execute(
            select(KnowledgeItem).where(
                KnowledgeItem.org_id == org_id,
                KnowledgeItem.category == "feature_registry",
                KnowledgeItem.is_active.is_(True),
            )
        )
        features = list(features_result.scalars().all())
        log(f"--- Active Features ({len(features)}) ---")

        null_embed = 0
        no_repo_link = 0
        for f in features:
            repo_links = await db.execute(
                select(KnowledgeRepoLink).where(KnowledgeRepoLink.knowledge_id == f.id)
            )
            links = list(repo_links.scalars().all())

            has_embed = f.embedding is not None
            if not has_embed:
                null_embed += 1

            repo_names = []
            for link in links:
                # Get repo name
                repo_result = await db.execute(
                    select(TrackedRepository.name).where(TrackedRepository.id == link.repo_id)
                )
                rname = repo_result.scalar_one_or_none() or "???"
                repo_names.append(rname)

            if not links:
                no_repo_link += 1

            log(f"  {f.title}")
            log(
                f"    source={f.source}  status={f.feature_status}  "
                f"embed={'YES' if has_embed else 'NULL'}  "
                f"repos={repo_names or 'NONE'}"
            )
            if links:
                for link in links:
                    locs = link.code_locations or {}
                    locs_summary = {k: len(v) for k, v in locs.items()} if locs else "EMPTY"
                    log(
                        f"    junction: repo_id={str(link.repo_id)[:8]}  "
                        f"code_locations={locs_summary}"
                    )
        log()
        log(
            f"  SUMMARY: {len(features)} features, {null_embed} NULL embeddings, "
            f"{no_repo_link} without repo links"
        )
        log()

        # --- Skill Profiles ---
        profiles_result = await db.execute(
            select(
                SkillProfile,
                User.name.label("user_name"),
                User.email,
            )
            .join(User, SkillProfile.user_id == User.id)
            .where(SkillProfile.org_id == org_id)
            .order_by(SkillProfile.skill_score.desc())
        )
        profiles = list(profiles_result.all())
        log(f"--- Skill Profiles ({len(profiles)}) ---")

        null_feature = 0
        empty_lang = 0
        for sp, user_name, email in profiles:
            has_feature = sp.feature_id is not None
            if not has_feature:
                null_feature += 1
            langs = sp.languages or []
            if not langs:
                empty_lang += 1

            # Resolve feature title
            feat_title = ""
            if sp.feature_id:
                feat_result = await db.execute(
                    select(KnowledgeItem.title).where(KnowledgeItem.id == sp.feature_id)
                )
                feat_title = feat_result.scalar_one_or_none() or "???"

            log(f"  {user_name:20s}  {email:30s}  module={sp.module}")
            log(
                f"    score={sp.skill_score:.2f}  touches={sp.touch_count}  "
                f"langs={langs}  feature_id={'YES → ' + feat_title if feat_title else 'NULL'}"
            )
        log()
        log(
            f"  SUMMARY: {len(profiles)} profiles, {null_feature} NULL feature_id, "
            f"{empty_lang} empty languages"
        )
        log()

        # --- Feature Map (what load_feature_map would produce) ---
        from app.services.scan_helpers import load_feature_map

        feature_map = await load_feature_map(db, org_id)
        log(f"--- Feature Map ({len(feature_map)} entries) ---")
        for name, paths, _fid in feature_map:
            log(f"  {name}")
            log(f"    paths={paths[:5]}{'...' if len(paths) > 5 else ''}")
        log()

        # --- Config ---
        config = dict(org.config or {})
        knowledge_cfg = config.get("knowledge", {})
        log("--- Org Config (knowledge) ---")
        log(f"  last_commit_sha: {knowledge_cfg.get('last_commit_sha', 'NONE')}")
        repo_shas = knowledge_cfg.get("repo_shas", {})
        for rp, sha in repo_shas.items():
            log(f"  repo_sha: {Path(rp).name} → {sha[:8]}")
        last_scan = knowledge_cfg.get("last_scan", {})
        if last_scan:
            log(f"  last_scan: {last_scan}")
        log()

    # Write to file if requested
    if output_file:
        Path(output_file).write_text("\n".join(lines))
        print(f"\nOutput written to {output_file}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze scan pipeline results")
    parser.add_argument("--output", "-o", help="Write output to file")
    args = parser.parse_args()
    asyncio.run(run_analysis(args.output))


if __name__ == "__main__":
    main()
