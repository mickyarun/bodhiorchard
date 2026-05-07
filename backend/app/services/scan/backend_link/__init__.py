# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Endpoint-grounded cross-layer linker.

Public surface:

* :func:`build_url_constants_map` / :func:`extract_api_paths` — frontend
  URL extraction with two-step constants map and per-feature call-site
  scan.
* :func:`build_store_map` — Nuxt auto-imported Pinia store resolver.
* :func:`build_index` / :class:`BackendIndex` — generic backend route
  indexer (NestJS / Express / Fastify / Koa / Flask / FastAPI).

The orchestration that ties these together for a scan run lives in
:mod:`app.services.scan.stages.backend_link` (the per-repo stage).
"""

from app.services.scan.backend_link.backend_indexer import (
    BackendIndex,
    RouteRecord,
    all_suffixes,
    build_index,
    iter_route_records,
)
from app.services.scan.backend_link.endpoint_extractor import (
    build_url_constants_map,
    extract_api_paths,
)
from app.services.scan.backend_link.linker_helpers import (
    BackendBucket,
    bucket_per_repo,
    resolve_seed_paths,
)
from app.services.scan.backend_link.nuxt_autoimport import build_store_map

__all__ = [
    "BackendBucket",
    "BackendIndex",
    "RouteRecord",
    "all_suffixes",
    "bucket_per_repo",
    "build_index",
    "build_store_map",
    "build_url_constants_map",
    "extract_api_paths",
    "iter_route_records",
    "resolve_seed_paths",
]
