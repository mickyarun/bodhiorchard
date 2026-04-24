// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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
const SCHEMA_VERSION = 1
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
 * TODO (you to implement): compute a stable, deterministic cache key for the
 * inputs above. The string it returns is used verbatim as the IndexedDB key,
 * so identical inputs MUST produce identical output across browser sessions
 * (no Math.random, no Date.now, no object-order dependence).
 *
 * DESIGN DECISION — what should invalidate the cache?
 *
 *   MORE invalidation (includes feature statuses in the hash)
 *     → any status change (planned → in_progress → implemented) re-grows
 *     → leaves re-appear the moment the first feature goes implemented
 *     → but most tree interactions trigger a full re-grow on reload
 *
 *   LESS invalidation (excludes statuses, keeps only titles + hasImplemented)
 *     → re-grow only when features are added / renamed / removed
 *     → status changes within the set stay instant
 *     → leaves don't move between implemented / not-implemented on reload
 *
 * Today the bake output depends on:
 *   - Every branch color comes from the trunk palette (repo-level, NOT status).
 *   - Leaves spawn only when ≥1 feature has status === 'implemented'.
 *   - Leaf color is derived from the trunk color alone.
 * So the status only affects cache output via the leaf-spawn gate.
 *
 * A short non-cryptographic hash (FNV-1a / djb2 / equivalent) is fine — this
 * is a cache key, not a security primitive. Keep it synchronous so callers
 * don't need to await.
 *
 * Aim for ~5–10 lines. Return a string ≤ 64 chars.
 */
export function computeCacheKey(_input: CacheKeyInput): string {
  // Placeholder — always-miss until you implement. Safe default: never cache.
  return `__unimplemented__${Math.random()}`
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
