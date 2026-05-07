# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Render a static HTML report of the cross-layer merge sandbox state.

Produces ``experiments/cross_layer_merge/report/report.html`` with five
sections, primarily oriented at the **merge** flow now (was originally
designed for the pair-verifier flow):

1. Stats strip — synth rows, active KIs, **multi-repo KI fraction**, etc.
2. Repos grid — classification + per-repo synth/KI counts.
3. Multi-repo KIs table — sorted by repo count desc, repo chips coloured by layer.
4. Per-repo KI sections — collapsible; spot over-fragmentation at a glance.
5. Pair verdicts — legacy section, still rendered if a ``verify`` run produced rows.
"""

from __future__ import annotations

import html
import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import func, select

from app.database import AsyncSessionLocal
from experiments.cross_layer_merge.merge.calibrate import calibrate_thresholds
from experiments.cross_layer_merge.report.compare import collect_stats
from experiments.cross_layer_merge.report.render_html_template import (
    MERGE_LOG_ROW,
    MULTI_REPO_KI_ROW,
    MULTI_REPO_KI_TABLE,
    PAGE_SHELL,
    PAIR_CARD,
    PER_REPO_KI_ROW,
    PER_REPO_SECTION,
    REPO_CARD,
    VERDICT_ROW,
)
from experiments.cross_layer_merge.schema import (
    XLMKnowledgeItem,
    XLMKnowledgeRepoLink,
    XLMMergeLog,
    XLMMergeOutcome,
    XLMPairLog,
    XLMPairPlan,
    XLMSynthesizedFeature,
    XLMTrackedRepo,
)


@dataclass
class RepoSummary:
    """Per-repo aggregates surfaced in the repos grid + KI sections."""

    repo: XLMTrackedRepo
    synth_count: int
    ki_count: int
    shared_count: int  # KIs that link to ≥2 repos


@dataclass
class KIWithRepos:
    """One KI plus the repos it spans (for the multi-repo table + per-repo sections)."""

    ki: XLMKnowledgeItem
    repo_ids: list[uuid.UUID]


@dataclass
class VerdictView:
    """Flattened view of one Claude verdict for the legacy pair-verifier rows."""

    action: str
    rationale: str
    source_repo: str
    source_title: str
    candidates: list[tuple[str, str, bool]]


async def _load_repos() -> list[XLMTrackedRepo]:
    async with AsyncSessionLocal() as session:
        return list(
            (await session.execute(select(XLMTrackedRepo).order_by(XLMTrackedRepo.name)))
            .scalars()
            .all()
        )


async def _load_kis_with_repos() -> list[KIWithRepos]:
    """Pull every active KI with its linked repo ids — single query for the merge view."""
    async with AsyncSessionLocal() as session:
        kis = list(
            (
                await session.execute(
                    select(XLMKnowledgeItem)
                    .where(XLMKnowledgeItem.is_active.is_(True))
                    .order_by(XLMKnowledgeItem.title)
                )
            )
            .scalars()
            .all()
        )
        links = (
            await session.execute(
                select(XLMKnowledgeRepoLink.knowledge_id, XLMKnowledgeRepoLink.repo_id)
            )
        ).all()

    by_ki: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for ki_id, repo_id in links:
        by_ki[ki_id].append(repo_id)
    return [KIWithRepos(ki=ki, repo_ids=by_ki.get(ki.id, [])) for ki in kis]


async def _count_synth_per_repo() -> dict[uuid.UUID, int]:
    """Count synthesized rows per repo for the per-repo summary card."""
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(
                    XLMSynthesizedFeature.repo_id,
                    func.count(XLMSynthesizedFeature.id),
                ).group_by(XLMSynthesizedFeature.repo_id)
            )
        ).all()
    return {repo_id: count for repo_id, count in rows}


async def _count_absorbed_synth() -> int:
    """Count synth rows that got folded into a canonical via merge."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(func.count(XLMSynthesizedFeature.id)).where(
                XLMSynthesizedFeature.merge_outcome == XLMMergeOutcome.MERGED_INTO
            )
        )
        return int(result.scalar_one())


async def _load_merge_log_with_lookups() -> tuple[
    list[XLMMergeLog],
    dict[uuid.UUID, XLMSynthesizedFeature],
]:
    """Pull the cluster-merge audit log + a synth lookup for prompt rendering."""
    async with AsyncSessionLocal() as session:
        rows = list(
            (await session.execute(select(XLMMergeLog).order_by(XLMMergeLog.created_at)))
            .scalars()
            .all()
        )
        synths = list((await session.execute(select(XLMSynthesizedFeature))).scalars().all())
    return rows, {s.id: s for s in synths}


def _render_merge_log(
    rows: list[XLMMergeLog],
    synth_lookup: dict[uuid.UUID, XLMSynthesizedFeature],
    repos_by_id: dict[uuid.UUID, XLMTrackedRepo],
) -> str:
    """Render each cluster decision as a collapsible card.

    Sort merges first (highest-signal — they consolidated rows), then
    no_match, then errors. Within a bucket, newest first.
    """
    if not rows:
        return (
            "<p class='dim'>No cluster decisions logged yet. Run "
            "<code>merge</code> after the audit log was wired up.</p>"
        )

    def sort_key(r: XLMMergeLog) -> tuple[int, float]:
        rank = {"merge": 0, "no_match": 1, "error": 2}.get(r.action or "", 3)
        return (rank, -r.created_at.timestamp() if r.created_at else 0.0)

    rendered = []
    for r in sorted(rows, key=sort_key):
        canonical = synth_lookup.get(r.canonical_synth_id)
        canonical_title = canonical.feature_title if canonical else str(r.canonical_synth_id)[:8]
        absorbed = set(r.absorbed_synth_ids or [])

        member_lines = []
        for mid in r.cluster_member_ids or []:
            synth = synth_lookup.get(mid)
            if synth is None:
                continue
            repo = repos_by_id.get(synth.repo_id)
            repo_chip = _render_repo_chip(repo) if repo else _esc(str(synth.repo_id)[:8])
            row_class = ""
            tag = ""
            if mid == r.canonical_synth_id:
                row_class = "canonical-row"
                tag = "<span class='tag' style='background:var(--blue)'>canonical</span>"
            elif mid in absorbed:
                row_class = "absorbed"
                tag = "<span class='tag'>absorbed</span>"
            member_lines.append(
                f"<li class='{row_class}'>{repo_chip}"
                f"<span style='flex:1'>{_esc(synth.feature_title)}</span>{tag}</li>"
            )

        related_block = ""
        if r.related_existing_ids:
            existing_chips = ", ".join(_esc(str(eid)[:8]) for eid in r.related_existing_ids)
            related_block = (
                "<div class='cluster-block'>"
                "<div class='label'>Related existing canonicals shown to Claude</div>"
                f"<div class='dim'>{existing_chips}</div>"
                "</div>"
            )

        action = r.action or "n/a"
        rationale = r.rationale or r.error or "(no rationale recorded)"
        prompt = r.prompt or ""
        response = r.response or "(no response)"

        rendered.append(
            MERGE_LOG_ROW.format(
                action=_esc(action),
                action_class=_esc(action),
                canonical_title=_esc(canonical_title),
                cluster_size=len(r.cluster_member_ids or []),
                absorbed_count=len(r.absorbed_synth_ids or []),
                rationale=_esc(rationale),
                member_list="\n".join(member_lines)
                or "<li class='dim'>(cluster members no longer present)</li>",
                related_block=related_block,
                prompt=_esc(prompt),
                response=_esc(response),
            )
        )
    return "\n".join(rendered)


async def _load_pairs() -> list[tuple[XLMPairPlan, str, str]]:
    """Return (pair, repo_a_name, repo_b_name) tuples ordered by start time."""
    async with AsyncSessionLocal() as session:
        rows = (
            (
                await session.execute(
                    select(XLMPairPlan).order_by(
                        XLMPairPlan.started_at.nullslast(), XLMPairPlan.id
                    )
                )
            )
            .scalars()
            .all()
        )
        repo_lookup: dict[uuid.UUID, str] = {
            r.id: r.name for r in (await session.execute(select(XLMTrackedRepo))).scalars().all()
        }
        return [
            (p, repo_lookup.get(p.repo_a_id, "?"), repo_lookup.get(p.repo_b_id, "?")) for p in rows
        ]


async def _load_verdicts_for_pair(pair_id: uuid.UUID) -> list[VerdictView]:
    async with AsyncSessionLocal() as session:
        log_rows = (
            (
                await session.execute(
                    select(XLMPairLog)
                    .where(XLMPairLog.pair_id == pair_id)
                    .order_by(XLMPairLog.created_at)
                )
            )
            .scalars()
            .all()
        )
        synths = (await session.execute(select(XLMSynthesizedFeature))).scalars().all()
        repos = (await session.execute(select(XLMTrackedRepo))).scalars().all()

    synth_lookup = {s.id: s for s in synths}
    repo_lookup = {r.id: r.name for r in repos}

    out: list[VerdictView] = []
    for r in log_rows:
        source = synth_lookup.get(r.source_synth_id)
        absorbed = set(r.absorbed_synth_ids or [])
        candidates: list[tuple[str, str, bool]] = []
        for cid in r.candidate_synth_ids or []:
            cand = synth_lookup.get(cid)
            if cand is None:
                continue
            candidates.append(
                (
                    repo_lookup.get(cand.repo_id, "?"),
                    cand.feature_title,
                    cid in absorbed,
                )
            )
        out.append(
            VerdictView(
                action=r.action or "?",
                rationale=r.rationale or "",
                source_repo=repo_lookup.get(source.repo_id, "?") if source else "?",
                source_title=source.feature_title if source else str(r.source_synth_id),
                candidates=candidates,
            )
        )
    return out


def _esc(text: str | None) -> str:
    return html.escape(text or "")


def _layer_class(repo: XLMTrackedRepo) -> str:
    """CSS class string for a repo's layer chip."""
    return repo.repo_layer.value if repo.repo_layer else "unclassified"


def _build_repo_summaries(
    repos: list[XLMTrackedRepo],
    synth_per_repo: dict[uuid.UUID, int],
    kis: list[KIWithRepos],
) -> list[RepoSummary]:
    """Roll up synth + KI counts per repo for the cards and the per-repo sections."""
    ki_count_per_repo: dict[uuid.UUID, int] = defaultdict(int)
    shared_count_per_repo: dict[uuid.UUID, int] = defaultdict(int)
    for ki_with in kis:
        is_shared = len(ki_with.repo_ids) >= 2
        for rid in ki_with.repo_ids:
            ki_count_per_repo[rid] += 1
            if is_shared:
                shared_count_per_repo[rid] += 1

    return [
        RepoSummary(
            repo=r,
            synth_count=synth_per_repo.get(r.id, 0),
            ki_count=ki_count_per_repo.get(r.id, 0),
            shared_count=shared_count_per_repo.get(r.id, 0),
        )
        for r in repos
    ]


def _render_repo_cards(summaries: list[RepoSummary]) -> str:
    cards = []
    for s in summaries:
        layer = s.repo.repo_layer.value if s.repo.repo_layer else "unclassified"
        cards.append(
            REPO_CARD.format(
                name=_esc(s.repo.name),
                layer=_esc(layer),
                layer_class=_esc(layer),
                tech=_esc(s.repo.tech_stack or "—"),
                db=_esc(s.repo.db_flavor or "—"),
                synth_count=s.synth_count,
                ki_count=s.ki_count,
                shared_count=s.shared_count,
            )
        )
    return "\n".join(cards) or "<p class='dim'>No repos copied. Run `copy-from-prod` first.</p>"


def _render_repo_chip(repo: XLMTrackedRepo) -> str:
    return f"<span class='repo-chip {_esc(_layer_class(repo))}'>{_esc(repo.name)}</span>"


def _render_multi_repo_table(
    kis: list[KIWithRepos],
    repos_by_id: dict[uuid.UUID, XLMTrackedRepo],
) -> str:
    """Sort multi-repo KIs by repo count desc, then by title."""
    multi = [k for k in kis if len(k.repo_ids) >= 2]
    multi.sort(key=lambda k: (-len(k.repo_ids), k.ki.title.lower()))
    if not multi:
        return (
            "<p class='dim'>No multi-repo KIs yet — every KI lives in exactly one repo. "
            "Try lowering the cross-layer threshold or relaxing the prompt's DECISION_RULES.</p>"
        )

    rows = []
    for k in multi:
        chips = "".join(
            _render_repo_chip(repos_by_id[rid]) for rid in k.repo_ids if rid in repos_by_id
        )
        rows.append(
            MULTI_REPO_KI_ROW.format(
                repo_count=len(k.repo_ids),
                title=_esc(k.ki.title),
                repo_chips=chips,
            )
        )
    return MULTI_REPO_KI_TABLE.format(rows="\n".join(rows))


def _render_per_repo_sections(
    summaries: list[RepoSummary],
    kis: list[KIWithRepos],
    repos_by_id: dict[uuid.UUID, XLMTrackedRepo],
) -> str:
    """One collapsible per repo, with KIs sorted: shared first, then alphabetical."""
    kis_by_repo: dict[uuid.UUID, list[KIWithRepos]] = defaultdict(list)
    for k in kis:
        for rid in k.repo_ids:
            kis_by_repo[rid].append(k)

    sections = []
    for s in summaries:
        repo_kis = kis_by_repo.get(s.repo.id, [])
        # Shared first (sorted by repo count desc), then single-repo alphabetical.
        repo_kis.sort(
            key=lambda k: (1 if len(k.repo_ids) < 2 else -len(k.repo_ids), k.ki.title.lower())
        )

        rows = []
        for k in repo_kis:
            other = [
                _render_repo_chip(repos_by_id[rid])
                for rid in k.repo_ids
                if rid != s.repo.id and rid in repos_by_id
            ]
            shared_class = "shared" if other else ""
            rows.append(
                PER_REPO_KI_ROW.format(
                    title=_esc(k.ki.title),
                    other_repos="".join(other) if other else "<span class='dim'>—</span>",
                    shared_class=shared_class,
                )
            )

        sections.append(
            PER_REPO_SECTION.format(
                repo_name=_esc(s.repo.name),
                layer=_esc(s.repo.repo_layer.value if s.repo.repo_layer else "unclassified"),
                layer_class=_esc(_layer_class(s.repo)),
                ki_count=s.ki_count,
                shared_count=s.shared_count,
                rows="\n".join(rows) or "<p class='dim'>No KIs linked to this repo.</p>",
            )
        )
    return "\n".join(sections)


def _render_verdicts(verdicts: list[VerdictView]) -> str:
    rows = []
    for v in verdicts:
        cand_html = "".join(
            f"<li class='{'absorbed' if absorbed else ''}'>"
            f"<strong>{_esc(repo)}</strong>: {_esc(title)}"
            f"{'  <span class=tag>absorbed</span>' if absorbed else ''}"
            "</li>"
            for repo, title, absorbed in v.candidates
        )
        rows.append(
            VERDICT_ROW.format(
                action=_esc(v.action),
                action_class=_esc(v.action),
                source_repo=_esc(v.source_repo),
                source_title=_esc(v.source_title),
                candidates=cand_html,
                rationale=_esc(v.rationale),
            )
        )
    return "\n".join(rows) or "<p class='dim'>No verdicts recorded for this pair.</p>"


def _render_pair_cards(cards: list[str]) -> str:
    return "\n".join(cards) or (
        "<p class='dim'>No pairs planned. Run `pair`+`verify` to populate this section. "
        "Cluster-merge runs do not write here.</p>"
    )


def _format_elapsed(pair: XLMPairPlan) -> str:
    if pair.started_at is None:
        return "—"
    if pair.finished_at is None:
        return "running"
    delta = (pair.finished_at - pair.started_at).total_seconds()
    return f"{int(delta)}s"


def _count_cross_layer_kis(
    kis: list[KIWithRepos],
    repos_by_id: dict[uuid.UUID, XLMTrackedRepo],
) -> int:
    """A KI is 'cross-layer' if its linked repos span 2+ distinct layers."""
    count = 0
    for k in kis:
        layers = {
            (repos_by_id[rid].repo_layer.value if repos_by_id[rid].repo_layer else "unknown")
            for rid in k.repo_ids
            if rid in repos_by_id
        }
        if len(layers) >= 2:
            count += 1
    return count


async def _count_synth_total() -> int:
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(func.count(XLMSynthesizedFeature.id)))
        return int(result.scalar_one())


async def render() -> str:
    """Build the full HTML page and return it as a string."""
    stats = await collect_stats()
    repos = await _load_repos()
    kis = await _load_kis_with_repos()
    synth_per_repo = await _count_synth_per_repo()
    synth_total = await _count_synth_total()
    absorbed_synth = await _count_absorbed_synth()
    pairs = await _load_pairs()

    repos_by_id = {r.id: r for r in repos}
    summaries = _build_repo_summaries(repos, synth_per_repo, kis)
    multi_repo_count = sum(1 for k in kis if len(k.repo_ids) >= 2)
    cross_layer_kis = _count_cross_layer_kis(kis, repos_by_id)
    merge_log_rows, merge_synth_lookup = await _load_merge_log_with_lookups()
    # Show the calibrated thresholds for the current synth pool. Re-running
    # the calibrator on demand keeps the HTML always-current without
    # persisting threshold state — the calibration is deterministic from
    # the synth rows alone.
    all_synths = list(merge_synth_lookup.values())
    calibrated = calibrate_thresholds(synth_rows=all_synths, repos=repos)

    pair_cards: list[str] = []
    for pair, repo_a, repo_b in pairs:
        verdicts = await _load_verdicts_for_pair(pair.id)
        pair_cards.append(
            PAIR_CARD.format(
                kind=_esc(pair.pair_kind),
                repo_a=_esc(repo_a),
                repo_b=_esc(repo_b),
                status=_esc(pair.status.value),
                status_class=_esc(pair.status.value),
                merged_count=pair.merged_count,
                elapsed=_format_elapsed(pair),
                verdicts=_render_verdicts(verdicts),
                verdict_count=len(verdicts),
            )
        )

    multi_repo_pct = (
        (stats.multi_repo_ki_count / stats.active_ki_count * 100) if stats.active_ki_count else 0.0
    )
    # Color the multi-repo headline by how it compares to prod's ~12% baseline.
    if multi_repo_pct >= 20:
        multi_repo_class = "good"
    elif multi_repo_pct >= 12:
        multi_repo_class = ""
    else:
        multi_repo_class = "warn"

    return PAGE_SHELL.format(
        synth_rows=synth_total,
        active_ki=stats.active_ki_count,
        inactive_ki=stats.inactive_ki_count,
        multi_repo=stats.multi_repo_ki_count,
        multi_repo_pct=f"{multi_repo_pct:.1f}",
        multi_repo_class=multi_repo_class,
        absorbed_synth=absorbed_synth,
        cross_layer_kis=cross_layer_kis,
        repo_count=len(repos),
        multi_repo_count=multi_repo_count,
        same_layer_threshold=f"{calibrated.same_layer:.3f}",
        cross_layer_threshold=f"{calibrated.cross_layer:.3f}",
        repos=_render_repo_cards(summaries),
        multi_repo_table=_render_multi_repo_table(kis, repos_by_id),
        per_repo_sections=_render_per_repo_sections(summaries, kis, repos_by_id),
        merge_log_count=len(merge_log_rows),
        merge_log=_render_merge_log(merge_log_rows, merge_synth_lookup, repos_by_id),
        pairs=_render_pair_cards(pair_cards),
    )
