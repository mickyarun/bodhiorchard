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
 * MaterialFactory — Centralized material creation with caching + LRU eviction.
 *
 * The old engine created materials ad-hoc with useLighting=false
 * (the root cause of black models). MaterialFactory creates properly
 * lit PBR materials and caches them by key to avoid duplicates.
 *
 * Key change: all materials use the default StandardMaterial pipeline
 * with useLighting=true (the default). Colors render correctly because
 * Application.ts sets up ACES tone mapping + sRGB gamma + IBL cubemap.
 *
 * Cache has a max size (default 256). When full, the least-recently-used
 * material with refCount=0 is evicted. This prevents GPU memory leaks
 * from materials that are acquired but never explicitly released.
 */
import * as pc from 'playcanvas'

interface CachedMaterial {
  material: pc.StandardMaterial
  refCount: number
  lastUsed: number  // monotonic counter for LRU eviction
}

const DEFAULT_MAX_CACHE = 512

export class MaterialFactory {
  private cache = new Map<string, CachedMaterial>()
  private maxCache: number
  private useCounter = 0

  constructor(maxCache = DEFAULT_MAX_CACHE) {
    this.maxCache = maxCache
  }

  /**
   * Get or create a basic PBR material with the given diffuse color.
   * Cached by key — same key returns the same material instance.
   */
  getColor(key: string, r: number, g: number, b: number, opts?: {
    metalness?: number
    gloss?: number
    emissive?: [number, number, number]
    opacity?: number
  }): pc.StandardMaterial {
    const cached = this.cache.get(key)
    if (cached) {
      cached.refCount++
      cached.lastUsed = ++this.useCounter
      return cached.material
    }

    // Evict if at capacity
    if (this.cache.size >= this.maxCache) {
      this.evictLRU()
    }

    const mat = new pc.StandardMaterial()
    mat.diffuse = new pc.Color(r, g, b)
    mat.metalness = opts?.metalness ?? 0
    mat.gloss = opts?.gloss ?? 0.3

    if (opts?.emissive) {
      mat.emissive = new pc.Color(opts.emissive[0], opts.emissive[1], opts.emissive[2])
    }

    if (opts?.opacity !== undefined && opts.opacity < 1) {
      mat.opacity = opts.opacity
      mat.blendType = pc.BLEND_NORMAL
    }

    mat.update()

    this.cache.set(key, { material: mat, refCount: 1, lastUsed: ++this.useCounter })
    return mat
  }

  /**
   * Release a cached material by key. Decrements refCount;
   * if zero, destroys the material.
   */
  release(key: string): void {
    const cached = this.cache.get(key)
    if (!cached) return

    cached.refCount--
    if (cached.refCount <= 0) {
      cached.material.destroy()
      this.cache.delete(key)
    }
  }

  /**
   * Evict the least-recently-used material with refCount <= 0.
   * If no zero-refCount entries exist, evict the oldest regardless (force cleanup).
   */
  private evictLRU(): void {
    let oldestKey: string | null = null
    let oldestTime = Infinity
    let oldestZeroKey: string | null = null
    let oldestZeroTime = Infinity

    for (const [key, entry] of this.cache) {
      if (entry.refCount <= 0 && entry.lastUsed < oldestZeroTime) {
        oldestZeroKey = key
        oldestZeroTime = entry.lastUsed
      }
      if (entry.lastUsed < oldestTime) {
        oldestKey = key
        oldestTime = entry.lastUsed
      }
    }

    // Prefer evicting unreferenced materials
    const evictKey = oldestZeroKey ?? oldestKey
    if (evictKey) {
      const entry = this.cache.get(evictKey)!
      entry.material.destroy()
      this.cache.delete(evictKey)
    }
  }

  /** Destroy all cached materials. */
  clear(): void {
    for (const [, cached] of this.cache) {
      cached.material.destroy()
    }
    this.cache.clear()
  }

  /** Current cache size (for debugging). */
  get size(): number {
    return this.cache.size
  }
}
