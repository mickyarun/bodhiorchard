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


# Path separators split a filepath into segments (one dir or filename at a time);
# within a segment we split on dots/underscores/hyphens and on camelCase boundaries.
# Keeping the two passes distinct lets us emit a kebab-joined compound *per segment*
# so a camelCase directory like ``orderShipment`` becomes the token ``order-shipment``
# instead of leaving the LLM-facing label to choose between the bare halves.
_PATH_SEPARATOR = re.compile(r"[/\\]+")
_SEGMENT_SPLIT = re.compile(r"[._\-]+|(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def extract_path_tokens(files: Iterable[str]) -> set[str]:
    """Return the meaningful token vocabulary for a set of file paths.

    Same blocked-token + camelCase + per-segment-bigram rules as
    :func:`label_cluster`, but returns just the *set* of tokens — callers
    that only need to test set membership (e.g. domain-overlap guards in
    the synthesis handler) shouldn't have to import the private Counter.
    """
    return set(_count_tokens(files).keys())


def extract_text_tokens(text: str) -> set[str]:
    """Return the meaningful token vocabulary for arbitrary text.

    Splits on non-alphanumerics, then re-applies camelCase splitting + the
    same blocked-token filter used for file paths. Lets callers compare a
    feature title or description against a cluster's path vocabulary on
    equal terms.

    Compound bigrams (``order-shipment``) are emitted only *within* a single
    contiguous run — a camelCase or hyphen/underscore-joined word like
    ``orderShipment`` produces ``{"order", "shipment", "order-shipment"}``.
    A space-separated phrase like ``"Order Shipment"`` produces
    ``{"order", "shipment"}`` without the bigram, because the separator
    breaks the run. That's by design: bigrams encode "these tokens belong
    together in the path/identifier", and free-form text doesn't give us
    that signal. Single-token overlap is enough for the guard, so the
    asymmetry is safe in practice.
    """
    tokens: set[str] = set()
    for raw in re.findall(r"[A-Za-z][A-Za-z0-9]*", text):
        for tok in _tokenise_segment(raw):
            tokens.add(tok)
    return tokens


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
        # No IDF signal — rank by raw count, but apply the same
        # compound-preference tiebreaker so multi-word domain nouns like
        # ``order-shipment`` don't lose to their bare halves when both
        # occur identically often.
        ranked = sorted(
            cluster_tokens.items(),
            key=lambda kv: (kv[1], "-" in kv[0], -len(kv[0])),
            reverse=True,
        )
        return _kebab(ranked[0][0])

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

    # Tiebreaker: on identical score+count, prefer compound forms (those with
    # an embedded ``-``) — they carry the multi-word domain noun
    # (``order-shipment``, ``bank-feed``) that single-token labels would
    # otherwise lose. We still fall back to shorter-token preference after that
    # so we don't pick noisy long tokens when the compound signal is absent.
    scored = sorted(
        cluster_tokens.items(),
        key=lambda kv: (
            score(kv[0], kv[1]),
            kv[1],
            "-" in kv[0],
            -len(kv[0]),
        ),
        reverse=True,
    )
    if not scored:
        return fallback
    return _kebab(scored[0][0])


def _count_tokens(files: Iterable[str]) -> Counter[str]:
    """Tokenise paths and count occurrences, dropping noise tokens.

    For each path segment with two-or-more non-blocked tokens, also emits a
    kebab-joined compound (``order-shipment``) so multi-word domain names
    survive the bag-of-tokens reduction.
    """
    counter: Counter[str] = Counter()
    for f in files:
        for segment in _PATH_SEPARATOR.split(f):
            for tok in _tokenise_segment(segment):
                counter[tok] += 1
    return counter


def _tokenise_segment(segment: str) -> list[str]:
    """Split one path segment into tokens + emit adjacent-pair compounds.

    Returns lowercased tokens. For each adjacent pair of non-blocked tokens in
    the segment, also emits the kebab-joined bigram (``order-shipment``,
    ``shipment-batch``). Bigrams rather than one full compound keep the
    two-word domain noun consistent across sibling segments of different
    lengths (``OrderShipmentService`` vs ``OrderShipmentServiceBatch``) — both
    contribute to the same bigram count, so the dominant 2-word domain name
    wins TF-IDF cleanly instead of being diluted across multiple ad-hoc
    compounds.
    """
    if not segment:
        return []
    parts = [t.lower() for t in _SEGMENT_SPLIT.split(segment) if t]
    cleaned = [p for p in parts if p not in _BLOCKED_TOKENS and not p.isdigit()]
    if len(cleaned) < 2:
        return cleaned
    bigrams = [f"{a}-{b}" for a, b in zip(cleaned, cleaned[1:], strict=False)]
    return [*cleaned, *bigrams]


def _kebab(token: str) -> str:
    """Return a lowercase kebab-case form, collapsing repeated separators."""
    s = re.sub(r"[^a-zA-Z0-9]+", "-", token).strip("-").lower()
    return s or token.lower()
