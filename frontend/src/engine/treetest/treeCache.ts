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
 * treeCache — IndexedDB-backed cache for baked procedural trees.
 *
 * After Tree3DSystem.bakeInstanced() collapses a fully-grown tree into a few
 * hardware-instanced draw calls, the "bake output" is just a small set of
 * Float32Arrays (per-branch / per-leaf world matrices) plus a handful of
 * scalar values (primary-branch midpoints, label Y). That entire structure is
 * structured-cloneable, so we write it straight into IndexedDB keyed by a
 * hash of the inputs that shape it.
 *
 * On the next page load, if the same inputs still produce the same hash,
 * ProceduralTreeSystem can skip growth + bake entirely and reconstruct the
 * instanced MeshInstances directly from the cached matrices. The user sees
 * the final tree immediately instead of the ~2 s grow-in animation.
 *
 * Storage format is deliberately low-level — raw TypedArrays, no JSON — so
 * reads and writes are effectively zero-copy and don't stall the main thread.
 */

const DB_NAME = 'bodhiorchard-tree-cache'
const STORE = 'trees'
// Schema history (newest at the bottom — read top-down to follow the timeline):
//
// v1: original — branches and leaves baked with absolute world coords.
//
// v2: tree branches grow at LOCAL origin (treeRoot owns world position).
//     v1 caches stored absolute world coords and would render at the
//     pre-Phase-2 baseline orchard position regardless of current scale,
//     so v1 entries must be invalidated.
//
// v3: leaf bake matrices switched from world transforms to local transforms
//     (leafRoot is parented under treeRoot, so the renderer applies
//     treeRoot.world × instance_matrix at draw time — storing world matrices
//     double-applied the tree offset and drifted leaves to 2× the tree
//     position). v2 caches written between the v1→v2 schema bump and this
//     fix contain bad world-space leaf matrices and must be invalidated.
export const SCHEMA_VERSION = 3
const DEFAULT_MAX_ENTRIES = 50

// ─── Cached data shape ───────────────────────────────────────────────────────

/** One per unique branch color. */
export interface BakedBranchGroup {
  colorKey: string
  color:    [number, number, number]   // 0-255 RGB, for material reconstruction
  matrices: Float32Array                // length = count * 16 (column-major mat4)
  count:    number
}

/** Single-material leaves per tree; null when the repo has no implemented features. */
export interface BakedLeafGroup {
  color:    [number, number, number]
  matrices: Float32Array
  count:    number
}

/** Invisible pick proxy per primary feature branch. */
export interface BakedFeaturePrimary {
  title:    string
  status:   string
  midpoint: [number, number, number]
}

export interface BakedTree {
  schemaVersion: typeof SCHEMA_VERSION
  cacheKey:      string
  savedAt:       number                        // epoch ms — used by pruneLRU
  branchGroups:  BakedBranchGroup[]
  leafGroup:     BakedLeafGroup | null
  primaries:     BakedFeaturePrimary[]
  labelY:        number
}

// ─── Cache-key hash ──────────────────────────────────────────────────────────

/**
 * Inputs that shape a baked tree's visual result. Anything here that changes
 * between sessions should invalidate the cached entry and trigger a re-grow.
 */
export interface CacheKeyInput {
  repoName:        string
  trunkColorIndex: number
  features:        Array<{ title: string; status: string }>
}

/**
 * Stable, deterministic cache key for a baked tree.
 *
 * Hashes only the inputs that actually shape the bake output:
 *   - repoName + trunkColorIndex (drive branch + leaf colors)
 *   - sorted feature titles (drive primary-branch identity + count)
 *   - hasImplemented bool (gates leaf spawn — the only status-driven visual)
 *
 * Per-feature statuses are intentionally excluded: flips that don't cross the
 * implemented threshold don't change bake output, so including them would
 * re-grow on every status change for no visual difference.
 *
 * U+0001 separator avoids collisions if a title ever contains '|'.
 * FNV-1a 32-bit — non-cryptographic but well-distributed for ASCII inputs.
 */
export function computeCacheKey(input: CacheKeyInput): string {
  const hasImpl = input.features.some(f => f.status === 'implemented') ? 1 : 0
  const titles  = input.features.map(f => f.title).sort()
  const canon   = `${input.repoName}|${input.trunkColorIndex}|${hasImpl}|${titles.join('')}`
  let h = 0x811c9dc5
  for (let i = 0; i < canon.length; i++) {
    h ^= canon.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  return (h >>> 0).toString(16).padStart(8, '0')
}

// ─── IndexedDB access ────────────────────────────────────────────────────────

let dbPromise: Promise<IDBDatabase> | null = null

function openDb(): Promise<IDBDatabase> {
  if (dbPromise) return dbPromise
  dbPromise = new Promise<IDBDatabase>((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, SCHEMA_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE)) {
        db.createObjectStore(STORE, { keyPath: 'cacheKey' })
      }
    }
    req.onsuccess = () => resolve(req.result)
    req.onerror   = () => reject(req.error)
  })
  return dbPromise
}

/** Returns the baked tree for the given key, or null on miss. */
export async function loadTreeCache(key: string): Promise<BakedTree | null> {
  if (key.startsWith('__unimplemented__')) return null
  try {
    const db = await openDb()
    return await new Promise<BakedTree | null>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly')
      const req = tx.objectStore(STORE).get(key)
      req.onsuccess = () => {
        const result = req.result as BakedTree | undefined
        if (!result || result.schemaVersion !== SCHEMA_VERSION) return resolve(null)
        resolve(result)
      }
      req.onerror = () => reject(req.error)
    })
  } catch {
    return null
  }
}

export async function saveTreeCache(data: BakedTree): Promise<void> {
  if (data.cacheKey.startsWith('__unimplemented__')) return
  try {
    const db = await openDb()
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite')
      tx.objectStore(STORE).put(data)
      tx.oncomplete = () => resolve()
      tx.onerror    = () => reject(tx.error)
    })
  } catch {
    // Swallow — a failed cache write should never break growth.
  }
}

/** Evict oldest entries until the store holds ≤ max. */
export async function pruneLRU(max = DEFAULT_MAX_ENTRIES): Promise<void> {
  try {
    const db = await openDb()
    const entries: Array<{ cacheKey: string; savedAt: number }> = await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, 'readonly')
      const req = tx.objectStore(STORE).getAll()
      req.onsuccess = () => resolve((req.result as BakedTree[]).map(e => ({ cacheKey: e.cacheKey, savedAt: e.savedAt })))
      req.onerror   = () => reject(req.error)
    })
    if (entries.length <= max) return
    entries.sort((a, b) => a.savedAt - b.savedAt)
    const toDelete = entries.slice(0, entries.length - max)
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(STORE, 'readwrite')
      const store = tx.objectStore(STORE)
      for (const e of toDelete) store.delete(e.cacheKey)
      tx.oncomplete = () => resolve()
      tx.onerror    = () => reject(tx.error)
    })
  } catch {
    // ignore
  }
}
