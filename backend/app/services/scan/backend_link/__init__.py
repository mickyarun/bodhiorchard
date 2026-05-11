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
