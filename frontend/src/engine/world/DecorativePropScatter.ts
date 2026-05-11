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
 * DecorativePropScatter — Flower patches + rock piles in the mid-distance
 * grass wedges.
 *
 * Complements (doesn't duplicate) `BushSystem`, which already scatters
 * single bushes + stumps near paths. This system adds:
 *   - flowerPatch  (60%) — tight cluster of 4–6 scaled-up flowers,
 *                          the unique color-accent element at zoom-out
 *   - rockCluster  (30%) — 2–4 rocks grouped into a visual pile
 *                          (BushSystem places only single rocks)
 *   - stumpOrLog   (10%) — rare accent
 *
 * Scatter region: annulus r=25..50, avoiding zones + path corridors.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { AssetLoader } from '../assets/AssetLoader'
import {
  SCATTER_ROCKS,
  SCATTER_FLOWERS,
  DECOR,
} from '../assets/AssetManifest'
import { evalRouteAt, type PathRoute } from '@shared/world/paths'
import {
  isInsideAnyZone,
  randRange,
  type ExclusionZone,
} from '../utils/MathUtils'

// ─── Scatter region (annulus) ────────────────────────────────────────────
const INNER_R = 24          // outside orchard plaza rim (plaza = r~7, repo trees end ~r=14)
const OUTER_R = 50          // inside the tree belt inner edge (r=55)
const TOTAL_CLUSTERS = 20   // additive to BushSystem's ~33 — moderate extra density
const MIN_CLUSTER_SPACING = 6.0

/** Minimum distance from a primary path centerline — no props on sidewalks. */
const PATH_CLEARANCE = 3.2
/** How many samples along each path we reject against. With PATH_CLEARANCE=3.2
 *  on paths up to ~40u long, 24 samples gives ~1.7u between world-space
 *  points even on curved Bezier paths (which have uneven t→world spacing).
 *  Ensures no prop sneaks between samples closer than PATH_CLEARANCE. */
const PATH_SAMPLES = 24

// ─── Cluster type mix ────────────────────────────────────────────────────
type ClusterType = 'flowerPatch' | 'rockCluster' | 'stumpOrLog'
const CLUSTER_WEIGHTS: Array<{ type: ClusterType; weight: number }> = [
  { type: 'flowerPatch', weight: 0.60 },
  { type: 'rockCluster', weight: 0.30 },
  { type: 'stumpOrLog',  weight: 0.10 },
]

// ─── Flower patch tuning ─────────────────────────────────────────────────
const FLOWERS_PER_PATCH_MIN = 4
const FLOWERS_PER_PATCH_MAX = 6
const FLOWER_PATCH_SPREAD = 1.4
/** Default flower GLBs are tiny — invisible at overhead camera. Scale up
 *  so the color accents actually read from distance. Matches the scale
 *  treatment in HubAnchor's bush ring. */
const FLOWER_SCALE_MIN = 1.8
const FLOWER_SCALE_MAX = 2.4

// ─── Rock cluster tuning ─────────────────────────────────────────────────
const ROCKS_PER_CLUSTER_MIN = 2
const ROCKS_PER_CLUSTER_MAX = 4
const ROCK_CLUSTER_SPREAD = 1.0
const ROCK_SCALE_MIN = 0.7
const ROCK_SCALE_MAX = 1.3

// ─── Stump tuning ────────────────────────────────────────────────────────
const STUMP_SCALE_MIN = 0.8
const STUMP_SCALE_MAX = 1.2

const STUMP_LOG_PATHS = [
  DECOR.stumpOld,
  DECOR.stumpRound,
  DECOR.logStack,
] as const

export class DecorativePropScatter {
  private root: pc.Entity | null = null

  async build(
    app: Application,
    loader: AssetLoader,
    exclusionZones: readonly ExclusionZone[],
    routes: readonly PathRoute[],
  ): Promise<pc.Entity> {
    this.root = new pc.Entity('DecorativePropScatter')
    app.root.addChild(this.root)

    // All of these are already preloaded via getEnvironmentGLBs() —
    // loadBatch() returns warm-cache handles.
    const [rocks, stumps, flowers] = await Promise.all([
      loader.loadBatch(SCATTER_ROCKS),
      loader.loadBatch([...STUMP_LOG_PATHS]),
      loader.loadBatch(SCATTER_FLOWERS),
    ])

    // Pre-sample primary paths once so path-clearance checks are O(clusters × samples)
    // rather than O(clusters × bezier-eval-overhead).
    const pathSamples = this.precomputePathSamples(routes)

    const centers = this.scatterCenters(TOTAL_CLUSTERS, exclusionZones, pathSamples)
    for (const c of centers) {
      const type = this.pickClusterType()
      switch (type) {
        case 'flowerPatch': this.spawnFlowerPatch(loader, flowers, c.x, c.z); break
        case 'rockCluster': this.spawnRockCluster(loader, rocks, c.x, c.z); break
        case 'stumpOrLog':  this.spawnStumpOrLog(loader, stumps, c.x, c.z); break
      }
    }

    return this.root
  }

  /** Pre-sample points along each primary path for fast clearance checks. */
  private precomputePathSamples(
    routes: readonly PathRoute[],
  ): Array<{ x: number; z: number }> {
    const out: Array<{ x: number; z: number }> = []
    for (const route of routes) {
      if ((route.kind ?? 'primary') !== 'primary') continue
      for (let i = 0; i <= PATH_SAMPLES; i++) {
        const t = i / PATH_SAMPLES
        out.push(evalRouteAt(route, t))
      }
    }
    return out
  }

  /**
   * Poisson-disc-ish scatter in the annulus r=INNER_R..OUTER_R.
   * Rejects points inside zones or within PATH_CLEARANCE of any path sample.
   */
  private scatterCenters(
    count: number,
    exclusionZones: readonly ExclusionZone[],
    pathSamples: Array<{ x: number; z: number }>,
  ): Array<{ x: number; z: number }> {
    const points: Array<{ x: number; z: number }> = []
    const maxAttempts = count * 25
    const minSpaceSq = MIN_CLUSTER_SPACING * MIN_CLUSTER_SPACING
    const pathClearSq = PATH_CLEARANCE * PATH_CLEARANCE

    for (let attempt = 0; attempt < maxAttempts && points.length < count; attempt++) {
      const angle = Math.random() * Math.PI * 2
      // Uniform-area radius: uniform in r² so points are spread evenly by area.
      const rSq = INNER_R * INNER_R + Math.random() * (OUTER_R * OUTER_R - INNER_R * INNER_R)
      const r = Math.sqrt(rSq)
      const x = Math.cos(angle) * r
      const z = Math.sin(angle) * r

      if (isInsideAnyZone(x, z, exclusionZones)) continue

      let tooClosePath = false
      for (const p of pathSamples) {
        const dx = x - p.x
        const dz = z - p.z
        if (dx * dx + dz * dz < pathClearSq) { tooClosePath = true; break }
      }
      if (tooClosePath) continue

      let tooCloseExisting = false
      for (const p of points) {
        const dx = x - p.x
        const dz = z - p.z
        if (dx * dx + dz * dz < minSpaceSq) { tooCloseExisting = true; break }
      }
      if (tooCloseExisting) continue

      points.push({ x, z })
    }
    return points
  }

  private pickClusterType(): ClusterType {
    const r = Math.random()
    let acc = 0
    for (const { type, weight } of CLUSTER_WEIGHTS) {
      acc += weight
      if (r <= acc) return type
    }
    return 'flowerPatch'
  }

  private spawnFlowerPatch(
    loader: AssetLoader, assets: pc.Asset[], cx: number, cz: number,
  ): void {
    const n = Math.floor(randRange(FLOWERS_PER_PATCH_MIN, FLOWERS_PER_PATCH_MAX + 1))
    for (let i = 0; i < n; i++) {
      const asset = assets[Math.floor(Math.random() * assets.length)]
      const flower = loader.instance(asset)
      const fx = cx + randRange(-FLOWER_PATCH_SPREAD, FLOWER_PATCH_SPREAD)
      const fz = cz + randRange(-FLOWER_PATCH_SPREAD, FLOWER_PATCH_SPREAD)
      flower.setPosition(fx, 0, fz)
      flower.setLocalEulerAngles(0, randRange(0, 360), 0)
      const s = randRange(FLOWER_SCALE_MIN, FLOWER_SCALE_MAX)
      flower.setLocalScale(s, s, s)
      this.root!.addChild(flower)
    }
  }

  private spawnRockCluster(
    loader: AssetLoader, assets: pc.Asset[], cx: number, cz: number,
  ): void {
    const n = Math.floor(randRange(ROCKS_PER_CLUSTER_MIN, ROCKS_PER_CLUSTER_MAX + 1))
    for (let i = 0; i < n; i++) {
      const asset = assets[Math.floor(Math.random() * assets.length)]
      const rock = loader.instance(asset)
      const rx = cx + randRange(-ROCK_CLUSTER_SPREAD, ROCK_CLUSTER_SPREAD)
      const rz = cz + randRange(-ROCK_CLUSTER_SPREAD, ROCK_CLUSTER_SPREAD)
      rock.setPosition(rx, 0, rz)
      rock.setLocalEulerAngles(0, randRange(0, 360), 0)
      const s = randRange(ROCK_SCALE_MIN, ROCK_SCALE_MAX)
      rock.setLocalScale(s, s, s)
      this.root!.addChild(rock)
    }
  }

  private spawnStumpOrLog(
    loader: AssetLoader, assets: pc.Asset[], x: number, z: number,
  ): void {
    const asset = assets[Math.floor(Math.random() * assets.length)]
    const prop = loader.instance(asset)
    prop.setPosition(x, 0, z)
    prop.setLocalEulerAngles(0, randRange(0, 360), 0)
    const s = randRange(STUMP_SCALE_MIN, STUMP_SCALE_MAX)
    prop.setLocalScale(s, s, s)
    this.root!.addChild(prop)
  }

  destroy(): void {
    if (this.root) {
      this.root.destroy()
      this.root = null
    }
  }
}
