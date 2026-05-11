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

# SPDX-License-Identifier: MIT
# Copyright (C) 2026 Arun Rajkumar

"""MCP handlers for code-graph queries.

Replaces the legacy ``mcp__gitnexus__*`` tool group. All handlers read
from ``repo_graph_cache`` (gzipped JSON node-link bytes written by the
ingest stage) and traverse the in-memory NetworkX graph.

Tool surface:

* ``code_impact`` — upstream/downstream BFS from a target symbol.
* ``code_query`` — text-rank search by label/source-file substring.
* ``code_context`` — single-symbol 360° (callers, callees, defines).
* ``code_community`` — list nodes belonging to a cluster id.
* ``code_god_nodes`` — high-centrality hubs (degree-ranked).
* ``code_stats`` — overall node/edge counts and language mix.

The traversal/ranking helpers below are adapted from graphify's own
``serve.py`` (MIT, https://github.com/safishamsi/graphify) — both
projects are MIT, attribution preserved here.

Each handler accepts ``(db, org, params)`` and returns a JSON-friendly
dict. They are registered in ``app.mcp.server`` alongside the BUD /
knowledge handlers.
"""

from __future__ import annotations

import unicodedata
import uuid
from typing import Any

import networkx as nx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.repositories.cluster_cache import ClusterCacheRepository
from app.repositories.repo_graph_cache import RepoGraphCacheRepository
from app.repositories.tracked_repository import TrackedRepoRepository

logger = structlog.get_logger(__name__)


_DEFAULT_DEPTH = 2
_MAX_DEPTH = 5
_DEFAULT_LIMIT = 10
_MAX_LIMIT = 100
_TEXT_BUDGET_TOKENS = 2000  # ~6KB human-readable subgraph dumps


# ── Public handlers ─────────────────────────────────────────────────


async def handle_code_impact(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Return upstream / downstream callers of ``target`` up to ``depth`` hops.

    Required params:
        target (str): symbol label or node id (case-insensitive).
        repo_id (str): UUID of the tracked repo.

    Optional params:
        direction (str): "upstream" (callers, default) or "downstream"
            (callees) or "both".
        depth (int): hop limit, default 2, cap 5.
    """
    target = str(params.get("target") or "").strip()
    repo_id_raw = params.get("repo_id")
    if not target or not repo_id_raw:
        return _err("target and repo_id are required")
    direction = str(params.get("direction") or "upstream").lower()
    if direction not in {"upstream", "downstream", "both"}:
        return _err("direction must be 'upstream', 'downstream', or 'both'")
    depth = min(int(params.get("depth") or _DEFAULT_DEPTH), _MAX_DEPTH)

    graph, head_sha = await _load_graph(db, org, repo_id_raw)
    if graph is None:
        return _err("no cached graph for this repo")

    matches = _find_nodes(graph, target)
    if not matches:
        return {"target": target, "matches": [], "head_sha": head_sha}

    walker = (
        graph
        if direction == "both" or not graph.is_directed()
        else (graph.reverse(copy=False) if direction == "upstream" else graph)
    )
    visited, edges = _bfs(walker, matches, depth)
    rendered = _render_subgraph(graph, visited, edges, token_budget=_TEXT_BUDGET_TOKENS)
    return {
        "target": target,
        "head_sha": head_sha,
        "direction": direction,
        "depth": depth,
        "matched_nodes": matches[:5],
        "node_count": len(visited),
        "edge_count": len(edges),
        "subgraph_text": rendered,
    }


async def handle_code_query(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Score nodes by substring overlap with the search terms.

    Required params:
        query (str): free-text search string.
        repo_id (str): UUID of the tracked repo.

    Optional params:
        limit (int): max nodes to return, default 10, cap 100.
    """
    query = str(params.get("query") or "").strip()
    repo_id_raw = params.get("repo_id")
    if not query or not repo_id_raw:
        return _err("query and repo_id are required")
    limit = min(int(params.get("limit") or _DEFAULT_LIMIT), _MAX_LIMIT)

    graph, head_sha = await _load_graph(db, org, repo_id_raw)
    if graph is None:
        return _err("no cached graph for this repo")

    terms = _split_query(query)
    scored = _score_nodes(graph, terms)[:limit]
    return {
        "query": query,
        "head_sha": head_sha,
        "results": [
            {
                "node_id": nid,
                "score": round(score, 3),
                "label": graph.nodes[nid].get("label"),
                "source_file": graph.nodes[nid].get("source_file"),
                "source_location": graph.nodes[nid].get("source_location"),
            }
            for score, nid in scored
        ],
    }


async def handle_code_context(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Return a single-symbol 360°: incoming callers + outgoing callees + attrs.

    Required params:
        symbol (str): symbol label or node id.
        repo_id (str): UUID of the tracked repo.
    """
    target = str(params.get("symbol") or "").strip()
    repo_id_raw = params.get("repo_id")
    if not target or not repo_id_raw:
        return _err("symbol and repo_id are required")

    graph, head_sha = await _load_graph(db, org, repo_id_raw)
    if graph is None:
        return _err("no cached graph for this repo")

    matches = _find_nodes(graph, target)
    if not matches:
        return {"symbol": target, "matches": [], "head_sha": head_sha}

    nid = matches[0]
    data = dict(graph.nodes[nid])
    incoming = list(graph.predecessors(nid)) if graph.is_directed() else []
    outgoing = list(graph.successors(nid)) if graph.is_directed() else list(graph.neighbors(nid))
    return {
        "symbol": target,
        "head_sha": head_sha,
        "node_id": nid,
        "attributes": data,
        "callers": [_node_summary(graph, n) for n in incoming[:25]],
        "callees": [_node_summary(graph, n) for n in outgoing[:25]],
    }


async def handle_code_community(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Return cluster metadata + members for a given cluster id.

    Required params:
        cluster_id (str): e.g. ``"c0"``.
        repo_id (str): UUID of the tracked repo.
    """
    cluster_id = str(params.get("cluster_id") or "").strip()
    repo_id_raw = params.get("repo_id")
    if not cluster_id or not repo_id_raw:
        return _err("cluster_id and repo_id are required")
    try:
        repo_id = uuid.UUID(str(repo_id_raw))
    except ValueError:
        return _err("repo_id is not a valid UUID")

    head_sha = await _resolve_head_sha(db, org, repo_id)
    if not head_sha:
        return _err("repo has no cached scan")

    cc_repo = ClusterCacheRepository(db, org_id=org.id)
    rows = await cc_repo.list_for_repo_sha(repo_id=repo_id, head_sha=head_sha)
    match = next((r for r in rows if r.cluster_id == cluster_id), None)
    if match is None:
        return {"cluster_id": cluster_id, "found": False, "head_sha": head_sha}
    return {
        "cluster_id": cluster_id,
        "found": True,
        "head_sha": head_sha,
        "label": match.label,
        "symbol_count": match.symbol_count,
        "cohesion": match.cohesion,
        "files": list(match.files or []),
        "symbols": list(match.symbols or []),
    }


async def handle_code_god_nodes(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Return the top-N highest-degree nodes in the graph (likely god classes/hubs).

    Required params:
        repo_id (str): UUID of the tracked repo.

    Optional params:
        limit (int): default 20, cap 100.
    """
    repo_id_raw = params.get("repo_id")
    if not repo_id_raw:
        return _err("repo_id is required")
    limit = min(int(params.get("limit") or 20), _MAX_LIMIT)

    graph, head_sha = await _load_graph(db, org, repo_id_raw)
    if graph is None:
        return _err("no cached graph for this repo")

    nodes_by_degree = sorted(graph.degree, key=lambda kv: kv[1], reverse=True)[:limit]
    return {
        "head_sha": head_sha,
        "top": [
            {
                "node_id": nid,
                "degree": int(deg),
                "label": graph.nodes[nid].get("label"),
                "source_file": graph.nodes[nid].get("source_file"),
            }
            for nid, deg in nodes_by_degree
        ],
    }


async def handle_code_stats(
    db: AsyncSession,
    org: Organization,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Return overall graph stats for the repo.

    Required params:
        repo_id (str): UUID of the tracked repo.
    """
    repo_id_raw = params.get("repo_id")
    if not repo_id_raw:
        return _err("repo_id is required")

    graph, head_sha = await _load_graph(db, org, repo_id_raw)
    if graph is None:
        return _err("no cached graph for this repo")

    file_counts: dict[str, int] = {}
    for _nid, data in graph.nodes(data=True):
        ext = ""
        src = data.get("source_file")
        if isinstance(src, str) and "." in src:
            ext = src.rsplit(".", 1)[-1].lower()
        if ext:
            file_counts[ext] = file_counts.get(ext, 0) + 1

    return {
        "head_sha": head_sha,
        "node_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(),
        "directed": graph.is_directed(),
        "file_extensions": dict(sorted(file_counts.items(), key=lambda kv: kv[1], reverse=True)),
    }


# ── Private helpers (adapted from graphify/serve.py, MIT) ──────────


async def _load_graph(
    db: AsyncSession,
    org: Organization,
    repo_id_raw: Any,
) -> tuple[nx.Graph | None, str | None]:
    """Resolve repo_id → latest head_sha → cached graph."""
    try:
        repo_id = uuid.UUID(str(repo_id_raw))
    except ValueError:
        return None, None
    head_sha = await _resolve_head_sha(db, org, repo_id)
    if not head_sha:
        return None, None
    rg_repo = RepoGraphCacheRepository(db, org_id=org.id)
    graph = await rg_repo.get_for_sha(repo_id=repo_id, head_sha=head_sha)
    return graph, head_sha


async def _resolve_head_sha(
    db: AsyncSession,
    org: Organization,
    repo_id: uuid.UUID,
) -> str | None:
    """Pick head_sha from tracked_repositories, fall back to cluster_cache latest."""
    tracked = await TrackedRepoRepository(db, org_id=org.id).get_by_id(repo_id)
    if tracked is not None and tracked.head_sha:
        return tracked.head_sha
    cc = ClusterCacheRepository(db, org_id=org.id)
    return await cc.latest_head_sha(repo_id=repo_id)


def _strip_diacritics(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _split_query(query: str) -> list[str]:
    """Split into lower-cased terms, dropping diacritics + 1-char tokens."""
    normalized = _strip_diacritics(query).lower()
    return [t for t in normalized.replace(",", " ").split() if len(t) > 1]


def _score_nodes(g: nx.Graph, terms: list[str]) -> list[tuple[float, str]]:
    """Score by term overlap with label (1.0/term) and source_file (0.5/term)."""
    scored: list[tuple[float, str]] = []
    for nid, data in g.nodes(data=True):
        label = _strip_diacritics(str(data.get("label") or "")).lower()
        source = (data.get("source_file") or "").lower()
        score = sum(1 for t in terms if t in label) + sum(0.5 for t in terms if t in source)
        if score > 0:
            scored.append((score, nid))
    scored.sort(key=lambda x: x[0], reverse=True)
    return scored


def _find_nodes(g: nx.Graph, target: str) -> list[str]:
    """Return node ids matching ``target`` by label or id, exact preferred.

    Match priority (case + diacritic insensitive):

    1. Exact node-id match.
    2. Exact label match.
    3. Substring-of-label match — only used as fallback when no exact
       match is found, and only when ``len(target) > 2`` so generic
       2-char queries like ``"db"`` don't sweep up every node containing
       that substring.

    Returning the most-specific match first prevents ``code_impact`` from
    expanding a 2-token target into hundreds of substring matches and
    blowing the BFS visited-set / token budget.
    """
    norm = _strip_diacritics(target).lower()
    exact_id: list[str] = []
    exact_label: list[str] = []
    substring: list[str] = []
    for nid, data in g.nodes(data=True):
        label = _strip_diacritics(str(data.get("label") or "")).lower()
        if norm == nid.lower():
            exact_id.append(nid)
        elif norm == label:
            exact_label.append(nid)
        elif len(norm) > 2 and norm in label:
            substring.append(nid)
    if exact_id:
        return exact_id
    if exact_label:
        return exact_label
    return substring


def _bfs(
    g: nx.Graph,
    starts: list[str],
    depth: int,
) -> tuple[set[str], list[tuple[str, str]]]:
    """Plain BFS expansion. Returns (visited nodes, edges traversed)."""
    visited: set[str] = set(starts)
    frontier: set[str] = set(starts)
    edges: list[tuple[str, str]] = []
    for _ in range(max(depth, 0)):
        next_frontier: set[str] = set()
        for n in frontier:
            for neighbor in g.neighbors(n):
                if neighbor not in visited:
                    next_frontier.add(neighbor)
                    edges.append((n, neighbor))
        if not next_frontier:
            break
        visited.update(next_frontier)
        frontier = next_frontier
    return visited, edges


def _render_subgraph(
    g: nx.Graph,
    nodes: set[str],
    edges: list[tuple[str, str]],
    *,
    token_budget: int,
) -> str:
    """Format a subgraph as plain-text NODE/EDGE lines, capped at token_budget."""
    char_budget = token_budget * 3
    lines: list[str] = []
    for nid in sorted(nodes, key=lambda n: g.degree(n), reverse=True):
        d = g.nodes[nid]
        line = (
            f"NODE {d.get('label', nid)} "
            f"[src={d.get('source_file', '')} loc={d.get('source_location', '')}]"
        )
        lines.append(line)
    for u, v in edges:
        if u in nodes and v in nodes:
            data = g.get_edge_data(u, v) or {}
            relation = data.get("relation", "")
            confidence = data.get("confidence", "")
            lines.append(
                f"EDGE {g.nodes[u].get('label', u)} --{relation} [{confidence}]--> "
                f"{g.nodes[v].get('label', v)}"
            )
    out = "\n".join(lines)
    if len(out) > char_budget:
        out = out[:char_budget] + f"\n... (truncated to ~{token_budget} tokens)"
    return out


def _node_summary(g: nx.Graph, nid: str) -> dict[str, Any]:
    """Compact dict of a single node for callers/callees lists."""
    if nid not in g:
        return {"node_id": nid}
    d = g.nodes[nid]
    return {
        "node_id": nid,
        "label": d.get("label"),
        "source_file": d.get("source_file"),
        "source_location": d.get("source_location"),
    }


def _err(message: str) -> dict[str, Any]:
    """Standard error envelope."""
    return {"error": message}


__all__ = [
    "handle_code_community",
    "handle_code_context",
    "handle_code_god_nodes",
    "handle_code_impact",
    "handle_code_query",
    "handle_code_stats",
]
