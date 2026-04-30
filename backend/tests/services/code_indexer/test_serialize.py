# SPDX-License-Identifier: MIT
# Copyright (C) 2026 Arun Rajkumar

"""Tests for ``app.services.code_indexer.serialize``."""

from __future__ import annotations

import gzip
import json

import networkx as nx
import pytest

from app.services.code_indexer.serialize import (
    graph_to_gzip_json,
    gzip_json_to_graph,
)


def test_round_trip_preserves_nodes_and_edges() -> None:
    g = nx.DiGraph()
    g.add_node("a", label="A", source_file="src/a.py")
    g.add_node("b", label="B", source_file="src/b.py")
    g.add_edge("a", "b", relation="calls", confidence="EXTRACTED")

    blob = graph_to_gzip_json(g)
    out = gzip_json_to_graph(blob)

    assert out.number_of_nodes() == 2
    assert out.number_of_edges() == 1
    assert out.nodes["a"]["source_file"] == "src/a.py"
    assert out.nodes["b"]["label"] == "B"


def test_empty_blob_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        gzip_json_to_graph(b"")


def test_non_gzip_blob_raises() -> None:
    with pytest.raises(ValueError, match="not valid gzip"):
        gzip_json_to_graph(b"not gzip content")


def test_invalid_json_inside_gzip_raises() -> None:
    blob = gzip.compress(b"not json")
    with pytest.raises(ValueError, match="not valid JSON"):
        gzip_json_to_graph(blob)


def test_missing_nodes_field_raises() -> None:
    blob = gzip.compress(json.dumps({"links": []}).encode())
    with pytest.raises(ValueError, match="missing 'nodes' list"):
        gzip_json_to_graph(blob)


def test_missing_links_field_raises() -> None:
    blob = gzip.compress(json.dumps({"nodes": []}).encode())
    with pytest.raises(ValueError, match="missing 'links' list"):
        gzip_json_to_graph(blob)


def test_node_without_id_raises() -> None:
    blob = gzip.compress(json.dumps({"nodes": [{"label": "x"}], "links": []}).encode())
    with pytest.raises(ValueError, match="must be an object with an 'id'"):
        gzip_json_to_graph(blob)


def test_link_without_endpoints_raises() -> None:
    payload = {
        "nodes": [{"id": "a"}, {"id": "b"}],
        "links": [{"source": "a"}],
    }
    blob = gzip.compress(json.dumps(payload).encode())
    with pytest.raises(ValueError, match="'source' and 'target'"):
        gzip_json_to_graph(blob)
