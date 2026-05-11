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

"""In-memory accumulator for synthesised features awaiting reconcile.

Per-(org_id, repo_id) buffer that the synth-feature MCP writer fills
during the LLM's tool-use loop. The synthesise scan stage drains the
buffer at end-of-batch and feeds it to
:mod:`app.services.feature_reconciler` which performs ALL DB writes
(insert / update / revive / mark inactive).

Why an in-memory accumulator rather than direct inserts:

* The reconciler needs to see the FULL synthesised set in one pass to
  apply layered identity matching (signature → Jaccard → cosine).
* Direct inserts during the LLM loop would trip the partial unique
  index ``ux_ftr_primary_title`` on duplicate-title cross-cluster
  cases — the reconciler resolves those by signature instead.
* Pre-prod local-dev: a process-level dict is plenty. Future scale-out
  can swap the backing store for Redis without touching callers.

Pairs with :mod:`app.mcp.synthesis_queue` (the cluster work-queue)
keyed off the same ``org_id:repo_name`` convention.
"""

from __future__ import annotations

from app.services.feature_reconciler import FeatureWrite

# Pending feature writes keyed by accumulator_key (str).
# accumulator_key matches synthesis_queue's queue_key convention so
# multi-repo parallel scans of one org don't collide.
_pending: dict[str, list[FeatureWrite]] = {}


def _key(org_id: str, *, repo_id: str) -> str:
    """Build the accumulator key. Uses repo_id (UUID string) for stability.

    Repo names can change mid-scan (rename); UUIDs cannot. The synthesise
    stage threads ``repo_id`` into the prompt so the MCP writer
    receives it verbatim.
    """
    return f"{org_id}:{repo_id}"


def accumulate(org_id: str, repo_id: str, write: FeatureWrite) -> int:
    """Append one ``FeatureWrite`` to the buffer for ``(org_id, repo_id)``.

    Returns the new buffer length so the MCP tool can echo a "queued
    N so far" status back to the LLM.
    """
    bucket = _pending.setdefault(_key(org_id, repo_id=repo_id), [])
    bucket.append(write)
    return len(bucket)


def drain(org_id: str, repo_id: str) -> list[FeatureWrite]:
    """Return and clear the buffer for ``(org_id, repo_id)``.

    Idempotent — a second drain returns ``[]``. Callers that want to
    inspect without consuming should use :func:`peek_count`.
    """
    return _pending.pop(_key(org_id, repo_id=repo_id), [])


def peek_count(org_id: str, repo_id: str) -> int:
    """Buffer length without consuming. For diagnostic logs."""
    return len(_pending.get(_key(org_id, repo_id=repo_id), []))


def peek_titles(org_id: str, repo_id: str) -> list[dict[str, str]]:
    """Snapshot the accumulator as ``[{title, description}, …]`` without draining.

    Used by the scan-status serializer to surface "features written so
    far" in the running ``feature_synthesis`` chip popover. The reconciler
    only writes to ``features`` at end-of-batch, so the DB is empty
    mid-synthesis — without this peek the popover shows nothing.
    """
    return [
        {"title": w.feature_title, "description": w.description}
        for w in _pending.get(_key(org_id, repo_id=repo_id), [])
    ]


def reset_for_org(org_id: str) -> None:
    """Drop every buffer for an org. Used by scan-cancel / failure paths."""
    prefix = f"{org_id}:"
    for key in [k for k in _pending if k.startswith(prefix)]:
        _pending.pop(key, None)
