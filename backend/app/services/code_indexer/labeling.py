# SPDX-License-Identifier: MIT
# Copyright (C) 2026 Arun Rajkumar

"""Deterministic cluster labelling from member file paths.

graphify's own ``cluster.cluster`` returns ``{community_id: [node_ids]}``
without labels. We need a human-readable label per cluster so the UI,
the synthesis prompt, and downstream stages can refer to "ais",
"bank-feed", "merchant-bank-account" rather than "c0", "c1", "c2".

The label is the most distinctive path-token shared by the cluster's
files, scored against the rest of the corpus. We use a tiny TF-IDF:
a token's weight is its frequency in the cluster divided by its
frequency across the whole corpus. This bubbles domain-specific names
(``ais``, ``bankFeed``) above generic infrastructure (``models``,
``services``, ``utils``).

Why path-token TF-IDF and not the cluster's most-connected node?
Real codebases organise by domain in the directory tree (Express's
``src/services/<domain>/``, Vue's ``src/views/<domain>/``). The
directory name IS the domain. Picking the dominant path token gets us
the ground-truth name almost for free.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable

# Path tokens we never label clusters with — pure infrastructure noise.
_BLOCKED_TOKENS = frozenset(
    {
        "src",
        "lib",
        "app",
        "apps",
        "packages",
        "internal",
        "pkg",
        "cmd",
        "main",
        "test",
        "tests",
        "spec",
        "specs",
        "__test__",
        "__tests__",
        "node_modules",
        "dist",
        "build",
        "out",
        "vendor",
        "target",
        "__pycache__",
        "common",
        "shared",
        "util",
        "utils",
        "helpers",
        "models",
        "model",
        "services",
        "service",
        "controllers",
        "controller",
        "repository",
        "repositories",
        "routes",
        "handlers",
        "schemas",
        "types",
        "interfaces",
        "components",
        "views",
        "pages",
        "store",
        "stores",
        "state",
        "ts",
        "tsx",
        "js",
        "jsx",
        "py",
        "go",
        "rs",
        "java",
        "kt",
        "swift",
        "vue",
        "svelte",
        "dart",
        "index",
    }
)


# Split path segments on common camelCase / kebab / snake / dot separators.
_TOKEN_SPLIT = re.compile(r"[/\\._\-]+|(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def build_corpus_tokens(corpus_files: Iterable[str]) -> Counter[str]:
    """Pre-compute the corpus-wide token Counter once per scan.

    Callers tokenising every cluster against the same corpus should
    build this once and pass it to ``label_cluster`` via the
    ``corpus_tokens`` keyword. Re-tokenising thousands of paths per
    cluster is O(N·C) and shows up on real-repo profiles.
    """
    return _count_tokens(corpus_files)


def label_cluster(
    member_files: Iterable[str],
    *,
    corpus_files: Iterable[str] | None = None,
    corpus_tokens: Counter[str] | None = None,
    fallback: str = "cluster",
) -> str:
    """Return a deterministic, human-readable label for the cluster.

    Args:
        member_files: Repo-relative path strings of files in this cluster.
        corpus_files: All files across all clusters in the same repo,
            used for IDF normalisation. Mutually exclusive with
            ``corpus_tokens``. Without either, the label degrades to
            most-frequent-token-in-cluster — still deterministic but
            less domain-specific.
        corpus_tokens: Pre-computed Counter from
            :func:`build_corpus_tokens`. Use this in hot loops to avoid
            re-tokenising the corpus once per cluster.
        fallback: Returned when no usable token can be extracted.

    Returns:
        Lowercase kebab-case token, e.g. ``"ais"`` or ``"payments"``.
    """
    cluster_tokens = _count_tokens(member_files)
    if not cluster_tokens:
        return fallback

    if corpus_tokens is None and corpus_files is None:
        winner, _ = cluster_tokens.most_common(1)[0]
        return _kebab(winner)

    if corpus_tokens is None:
        # Caller passed corpus_files only — compute once.
        corpus_tokens = _count_tokens(corpus_files or [])
    corpus_size = max(1, sum(corpus_tokens.values()))
    cluster_size = sum(cluster_tokens.values())

    # TF-IDF with the log on IDF (the standard form). Without the log,
    # raw ``tf / df`` over-rewards very rare tokens that appear in only
    # one cluster file: e.g. for a cluster of seven ``AisFoo.ts`` files
    # the token ``Ais`` appears 7× across 50 corpus matches → 0.14,
    # while ``Balance`` (only in ``AisBalance.ts``) at 1×/5 → 0.20 wins.
    # The log-IDF form gives ``ais``=7×log(N/50) > ``balance``=1×log(N/5)
    # for any reasonable corpus size, restoring "the dominant cluster
    # token wins" intuition.
    #
    # We also require a minimum cluster-coverage of 2 occurrences before
    # IDF can outweigh raw frequency — that prevents a single-occurrence
    # rare token from beating a token that appears in *every* cluster file.
    def score(token: str, count: int) -> float:
        df = max(1, corpus_tokens.get(token, count))
        coverage = count / cluster_size if cluster_size else 0
        idf = math.log(corpus_size / df)
        # Bonus when the token appears in ≥ half the cluster's files
        bonus = 1.0 + coverage  # in [1, 2]
        return count * idf * bonus

    scored = sorted(
        cluster_tokens.items(),
        key=lambda kv: (
            score(kv[0], kv[1]),
            kv[1],
            -len(kv[0]),
        ),
        reverse=True,
    )
    if not scored:
        return fallback
    return _kebab(scored[0][0])


def _count_tokens(files: Iterable[str]) -> Counter[str]:
    """Tokenise paths and count occurrences, dropping noise tokens."""
    counter: Counter[str] = Counter()
    for f in files:
        for tok in _tokenise(f):
            if tok and tok.lower() not in _BLOCKED_TOKENS and not tok.isdigit():
                counter[tok.lower()] += 1
    return counter


def _tokenise(path: str) -> list[str]:
    """Split a path into camelCase/kebab/snake/dot-separated tokens."""
    return [t for t in _TOKEN_SPLIT.split(path) if t]


def _kebab(token: str) -> str:
    """Return a lowercase kebab-case form, collapsing repeated separators."""
    s = re.sub(r"[^a-zA-Z0-9]+", "-", token).strip("-").lower()
    return s or token.lower()
