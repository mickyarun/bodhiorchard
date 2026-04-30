# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Render a static HTML report of the cross-layer merge sandbox state.

Generates ``experiments/cross_layer_merge/report/report.html`` with
sections for repo classifications, pair plan, and the per-verdict
merge log. Designed to be reopened in a browser after every ``verify``
run during prompt iteration.
"""

import html
import uuid
from dataclasses import dataclass

from sqlalchemy import select

from app.database import AsyncSessionLocal
from experiments.cross_layer_merge.report.compare import collect_stats
from experiments.cross_layer_merge.report.render_html_template import (
    PAGE_SHELL,
    PAIR_CARD,
    REPO_CARD,
    VERDICT_ROW,
)
from experiments.cross_layer_merge.schema import (
    XLMPairLog,
    XLMPairPlan,
    XLMSynthesizedFeature,
    XLMTrackedRepo,
)


@dataclass
class VerdictView:
    """Flattened view of one Claude verdict for the HTML row template."""

    action: str
    rationale: str
    source_repo: str
    source_title: str
    candidates: list[tuple[str, str, bool]]  # (repo_name, title, was_absorbed)


async def _load_repos() -> list[XLMTrackedRepo]:
    async with AsyncSessionLocal() as session:
        return list(
            (await session.execute(select(XLMTrackedRepo).order_by(XLMTrackedRepo.name)))
            .scalars()
            .all()
        )


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
    """One row per Claude verdict for a single pair, with feature titles resolved."""
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


def _render_repos(repos: list[XLMTrackedRepo]) -> str:
    cards = []
    for r in repos:
        layer = r.repo_layer.value if r.repo_layer else "unclassified"
        cards.append(
            REPO_CARD.format(
                name=_esc(r.name),
                layer=_esc(layer),
                layer_class=_esc(layer),
                tech=_esc(r.tech_stack or "—"),
                db=_esc(r.db_flavor or "—"),
            )
        )
    return "\n".join(cards)


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


async def render() -> str:
    """Build the full HTML page and return it as a string."""
    stats = await collect_stats()
    repos = await _load_repos()
    pairs = await _load_pairs()

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
    return PAGE_SHELL.format(
        active_ki=stats.active_ki_count,
        inactive_ki=stats.inactive_ki_count,
        multi_repo=stats.multi_repo_ki_count,
        multi_repo_pct=f"{multi_repo_pct:.1f}",
        pairs_done=stats.pairs_done,
        pairs_failed=stats.pairs_failed,
        total_merges=stats.total_merges,
        repos=_render_repos(repos),
        pairs=_render_pair_cards(pair_cards),
    )


def _render_pair_cards(cards: list[str]) -> str:
    return "\n".join(cards) or "<p class='dim'>No pairs planned. Run `pair` first.</p>"


def _format_elapsed(pair: XLMPairPlan) -> str:
    if pair.started_at is None:
        return "—"
    if pair.finished_at is None:
        return "running"
    delta = (pair.finished_at - pair.started_at).total_seconds()
    return f"{int(delta)}s"
