// Copyright 2025-2026 Arun Rajkumar
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * SceneDiff — classifies an EngineData change as full-rebuild, incremental,
 * or no-op, so `setData` can skip the teardown+rebuild for the common case
 * (a single repo's features/health changed, or relationships shifted).
 *
 * FAIL-CLOSED by design: anything this classifier doesn't explicitly prove
 * safe routes to a full rebuild. The incremental path may only fire when
 * the world layout is provably unchanged:
 *   - same repo names in the same order (repo count drives the orchard
 *     radius → tree positions, exclusion zones, scatter, paths)
 *   - byte-identical member list (members drive the housing village,
 *     physics bodies, and seat registry)
 *
 * Garden-irrelevant fields: `buds`, `threats`, and `feature_skills` are
 * consumed only by the separate GraphEngine view, never by the garden
 * scene build — changes to them alone are a no-op here.
 *
 * Pure module: no PlayCanvas imports, fully unit-testable.
 */
import type { EngineData, EngineFeature } from '../types'

export type SceneDiffResult =
  | { kind: 'none' }
  | { kind: 'incremental'; changedRepos: string[]; relationshipsChanged: boolean }
  | { kind: 'full'; reason: string }

/** Every key the classifier understands. A key present on either payload
 *  but absent here means a NEW data contract this classifier predates —
 *  route to full rebuild rather than silently ignoring it. */
const KNOWN_KEYS: ReadonlySet<string> = new Set([
  'repos', 'features', 'buds', 'threats', 'members',
  'agent_activity', 'relationships', 'feature_skills',
])

export function classifyDiff(prev: EngineData, next: EngineData): SceneDiffResult {
  for (const key of [...Object.keys(prev), ...Object.keys(next)]) {
    if (!KNOWN_KEYS.has(key)) {
      return { kind: 'full', reason: `unknown EngineData field: ${key}` }
    }
  }

  // Repo set/order — the layout anchor. Any change shifts every tree
  // position and exclusion zone.
  if (prev.repos.length !== next.repos.length) {
    return { kind: 'full', reason: 'repo count changed' }
  }
  for (let i = 0; i < prev.repos.length; i++) {
    if (prev.repos[i].repo_name !== next.repos[i].repo_name) {
      return { kind: 'full', reason: 'repo set/order changed' }
    }
  }

  // Members — drive village houses, physics bodies, seats. Any field
  // change (tier upgrades, renames, character swaps) → full.
  if (stableJson(prev.members) !== stableJson(next.members)) {
    return { kind: 'full', reason: 'members changed' }
  }

  // Per-repo signature: the repo row plus its (non-shadow) features —
  // exactly the inputs ProceduralTreeSystem bakes into one tree.
  const prevFeatures = featuresByRepo(prev.features)
  const nextFeatures = featuresByRepo(next.features)
  const changedRepos: string[] = []
  for (let i = 0; i < next.repos.length; i++) {
    const name = next.repos[i].repo_name
    const prevSig = stableJson(prev.repos[i]) + stableJson(prevFeatures.get(name) ?? [])
    const nextSig = stableJson(next.repos[i]) + stableJson(nextFeatures.get(name) ?? [])
    if (prevSig !== nextSig) changedRepos.push(name)
  }

  const relationshipsChanged =
    stableJson(sortedRelationships(prev)) !== stableJson(sortedRelationships(next))

  if (changedRepos.length === 0 && !relationshipsChanged) {
    return { kind: 'none' }
  }
  return { kind: 'incremental', changedRepos, relationshipsChanged }
}

/** Group features per repo, skipping `link_role === 'backend'` shadow rows —
 *  mirrors ProceduralTreeSystem.build's indexing exactly. */
function featuresByRepo(features: EngineFeature[]): Map<string, EngineFeature[]> {
  const out = new Map<string, EngineFeature[]>()
  for (const f of features) {
    if (!f.repo_name) continue
    if (f.link_role === 'backend') continue
    const arr = out.get(f.repo_name)
    if (arr) arr.push(f); else out.set(f.repo_name, [f])
  }
  return out
}

/** Relationships compared order-insensitively — upstream queries don't
 *  guarantee row order, and arc geometry doesn't depend on it. */
function sortedRelationships(data: EngineData): unknown[] {
  return data.relationships
    .map(r => stableJson(r))
    .sort()
}

/** JSON.stringify with sorted object keys, recursively — a stable
 *  structural signature regardless of property insertion order. */
function stableJson(value: unknown): string {
  return JSON.stringify(sortKeys(value))
}

function sortKeys(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortKeys)
  if (value !== null && typeof value === 'object') {
    const out: Record<string, unknown> = {}
    for (const key of Object.keys(value as Record<string, unknown>).sort()) {
      out[key] = sortKeys((value as Record<string, unknown>)[key])
    }
    return out
  }
  return value
}
