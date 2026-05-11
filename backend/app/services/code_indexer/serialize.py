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

"""Safe round-trip between NetworkX graphs and gzipped JSON bytes.

Two reasons we use NetworkX's JSON node-link format here instead of any
binary serialisation:

1. **Safety on read.** The graph blob lives in our DB. JSON
   deserialisation of an untrusted byte string produces only data —
   never callable code. Binary formats can execute arbitrary opcodes
   during unmarshalling, which is unsafe if the row is ever
   attacker-controlled.
2. **Forward-compatibility.** JSON node-link is a documented NetworkX
   format. We can read graphs written by future NetworkX versions and
   inspect the bytes by hand if a row is corrupt.

A 200KB graph compresses to roughly 30KB. The compress/decompress cost
is negligible (single-digit ms) compared to a Postgres round-trip.
"""

from __future__ import annotations

import gzip
import json
from typing import Any

import networkx as nx
from networkx.readwrite import json_graph

_MAX_DECOMPRESSED_BYTES = 256 * 1024 * 1024  # 256 MB safety cap


def graph_to_gzip_json(g: nx.Graph) -> bytes:
    """Serialise ``g`` to gzipped JSON node-link bytes."""
    payload = json_graph.node_link_data(g, edges="links")
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return gzip.compress(raw)


def gzip_json_to_graph(blob: bytes) -> nx.Graph:
    """Round-trip ``blob`` (from ``graph_to_gzip_json``) back to a graph.

    Validates structure before reconstructing so a corrupt row produces
    a controlled exception rather than silent data corruption.

    Raises:
        ValueError: blob is not valid gzip, not valid JSON, exceeds the
            decompressed-size cap, or doesn't have node-link shape.
    """
    if not blob:
        raise ValueError("graph blob is empty")
    try:
        raw = gzip.decompress(blob)
    except OSError as exc:
        raise ValueError(f"graph blob is not valid gzip: {exc}") from exc
    if len(raw) > _MAX_DECOMPRESSED_BYTES:
        raise ValueError(
            f"graph blob decompresses to {len(raw)} bytes (cap {_MAX_DECOMPRESSED_BYTES})"
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"graph blob is not valid JSON: {exc}") from exc
    _validate_node_link_shape(payload)
    try:
        return json_graph.node_link_graph(payload, edges="links")
    except (KeyError, TypeError) as exc:
        raise ValueError(f"graph blob is not in node-link form: {exc}") from exc


def _validate_node_link_shape(payload: Any) -> None:
    """Sanity check the JSON shape before handing it to NetworkX."""
    if not isinstance(payload, dict):
        raise ValueError("graph payload must be a JSON object")
    nodes = payload.get("nodes")
    links = payload.get("links")
    if not isinstance(nodes, list):
        raise ValueError("graph payload missing 'nodes' list")
    if not isinstance(links, list):
        raise ValueError("graph payload missing 'links' list")
    for n in nodes:
        if not isinstance(n, dict) or "id" not in n:
            raise ValueError("each node must be an object with an 'id' field")
    for e in links:
        if not isinstance(e, dict) or "source" not in e or "target" not in e:
            raise ValueError("each link must be an object with 'source' and 'target'")
