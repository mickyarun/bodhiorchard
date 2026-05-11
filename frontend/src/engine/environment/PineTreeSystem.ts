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
 * PineTreeSystem — Tiered forest belt framing the hub world.
 *
 * Two density bands + species variation make the tree ring read as
 * "intentional forest" rather than "procedural scatter":
 *
 *   1. Framing clumps (inner band, r≈38): 3 dense clusters at angular
 *      positions BETWEEN the activity/habitation zones. These frame
 *      sightlines from the hub toward each zone and hide the transition
 *      between zone groups — the eye sees a tree wall, not empty grass.
 *
 *   2. Outer perimeter (r=55..85): uniform-ish scatter with 2 angular
 *      "gaps" where no trees are placed — suggests paths disappearing
 *      into the forest beyond, adding implied world-beyond depth.
 *
 * Species variation: pine (dominant), tall-green, leafy, autumn — mixed
 * so no single silhouette repeats in a cluster. Occasional autumn tree
 * gives warm color accents without a fall-biome commitment.
 *
 * Hardware-instanced: 41 scatter points across 3 species GLBs collapse
 * into one draw call per (mesh, material) (≈3–6 draws total) instead of
 * 41 per-entity matrix uploads. Pine is the dominant draw-call cost in
 * the perimeter belt — instancing was the headline target of Tier B.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { AssetLoader } from '../assets/AssetLoader'
import { SCATTER_PINES, FOREST_TREES } from '../assets/AssetManifest'
import { isInsideAnyZone, randRange, type ExclusionZone } from '../utils/MathUtils'
import { getActiveScale } from '@shared/world/layoutScale'
import {
  buildInstancedGlbs, type GlbScatterGroup, type ScatterTransform,
} from '../utils/GlbInstancing'

// ─── Outer perimeter belt ────────────────────────────────────────────────
const OUTER_PINE_COUNT = 32
const MIN_DISTANCE = 4.5

const PERIMETER_GAPS_DEG: Array<{ center: number; halfWidth: number }> = [
  { center: 0,   halfWidth: 6 },   // due east
  { center: 180, halfWidth: 6 },   // due west
]

// ─── Inner framing clumps ────────────────────────────────────────────────
const FRAMING_TREES_PER_CLUMP = 3
const FRAMING_SPREAD = 3.5
const FRAMING_ANGLES_DEG = [90, 215, 325]

/**
 * Scale factor applied when species is NOT pine. The other GLBs in the
 * forest set (tree_tall_green, tree_autumn) have much larger default
 * bounds than pine_tree.glb — at pine's native scale they'd dwarf the
 * hub tree. 0.25 brings them into a pine-equivalent visual footprint.
 */
const NON_PINE_SCALE = 0.25

const PINE_SPECIES_IDX = 0   // index into the assets[] array below

/**
 * Species weights. `groupIdx` is the index into the `assets[]` / `groups[]`
 * arrays built in `build()` — same order as `speciesPaths`. Reordering
 * either array requires updating `groupIdx` here in lockstep.
 */
const SPECIES_WEIGHTS: Array<{ groupIdx: number; weight: number }> = [
  { groupIdx: 0, weight: 0.70 },  // pine_tree (strongly dominant)
  { groupIdx: 1, weight: 0.20 },  // tree_tall_green
  { groupIdx: 2, weight: 0.10 },  // tree_autumn (rare warm accent)
]

export class PineTreeSystem {
  private root: pc.Entity | null = null
  private vbs: pc.VertexBuffer[] = []

  async build(
    app: Application,
    loader: AssetLoader,
    exclusionZones: readonly ExclusionZone[],
  ): Promise<pc.Entity> {
    this.root = new pc.Entity('PineTreeSystem')

    const speciesPaths = [
      SCATTER_PINES[0],               // pine_tree      (pathIdx 0)
      FOREST_TREES[2],                // tree_tall_green (pathIdx 1)
      FOREST_TREES[4],                // tree_autumn    (pathIdx 2)
    ]
    const assets = await loader.loadBatch(speciesPaths)
    const groups: GlbScatterGroup[] = assets.map((asset) => ({
      asset, transforms: [],
    }))

    // 1. Outer perimeter belt — uniform scatter with angular gaps
    const outerPoints = this.outerRingScatter(
      OUTER_PINE_COUNT, MIN_DISTANCE, exclusionZones,
    )
    for (const pt of outerPoints) {
      this.assignTree(groups, pt.x, pt.z, randRange(3, 7))
    }

    // 2. Inner framing clumps — dense clusters at between-zone angles
    for (const angleDeg of FRAMING_ANGLES_DEG) {
      this.spawnClump(groups, angleDeg, exclusionZones)
    }

    const { entities, vbs } = buildInstancedGlbs(
      app.app.graphicsDevice,
      loader,
      groups,
      { namePrefix: 'PineInstanced' },
    )
    for (const e of entities) this.root.addChild(e)
    this.vbs = vbs

    app.root.addChild(this.root)
    return this.root
  }

  /**
   * Pick a species and append a transform to that group's bucket.
   * Non-pine species get NON_PINE_SCALE applied so their visual footprint
   * matches pine — the GLBs have inconsistent native bounds.
   */
  private assignTree(
    groups: GlbScatterGroup[], x: number, z: number, baseScale: number,
  ): void {
    const speciesIdx = this.pickWeightedSpecies()
    const speciesScale = speciesIdx === PINE_SPECIES_IDX ? 1.0 : NON_PINE_SCALE
    const transform: ScatterTransform = {
      x, y: 0, z,
      yawDeg: randRange(0, 360),
      scale:  baseScale * speciesScale,
    }
    groups[speciesIdx].transforms.push(transform)
  }

  private pickWeightedSpecies(): number {
    const r = Math.random()
    let acc = 0
    for (const { groupIdx, weight } of SPECIES_WEIGHTS) {
      acc += weight
      if (r <= acc) return groupIdx
    }
    return SPECIES_WEIGHTS[0].groupIdx
  }

  private outerRingScatter(
    count: number,
    minDist: number,
    exclusionZones: readonly ExclusionZone[],
  ): Array<{ x: number; z: number }> {
    const points: Array<{ x: number; z: number }> = []
    const maxAttempts = count * 20
    let attempts = 0

    while (points.length < count && attempts < maxAttempts) {
      attempts++
      const angleRad = Math.random() * Math.PI * 2
      const angleDeg = (angleRad * 180) / Math.PI
      if (this.isInGap(angleDeg)) continue

      const { pineRingInner, pineRingOuter } = getActiveScale().perimeter
      const r = pineRingInner + Math.random() * (pineRingOuter - pineRingInner)
      const x = Math.cos(angleRad) * r
      const z = Math.sin(angleRad) * r

      if (isInsideAnyZone(x, z, exclusionZones)) continue
      if (this.isTooCloseToExisting(x, z, points, minDist)) continue
      points.push({ x, z })
    }
    return points
  }

  private spawnClump(
    groups: GlbScatterGroup[],
    angleDeg: number,
    exclusionZones: readonly ExclusionZone[],
  ): void {
    const angleRad = (angleDeg * Math.PI) / 180
    const framingRadius = getActiveScale().perimeter.pineFramingRadius
    const cx = Math.cos(angleRad) * framingRadius
    const cz = Math.sin(angleRad) * framingRadius

    const placed: Array<{ x: number; z: number }> = []
    let attempts = 0
    while (placed.length < FRAMING_TREES_PER_CLUMP && attempts < 40) {
      attempts++
      const x = cx + randRange(-FRAMING_SPREAD, FRAMING_SPREAD)
      const z = cz + randRange(-FRAMING_SPREAD, FRAMING_SPREAD)
      if (isInsideAnyZone(x, z, exclusionZones)) continue
      if (this.isTooCloseToExisting(x, z, placed, 2.2)) continue
      placed.push({ x, z })
      this.assignTree(groups, x, z, randRange(4, 6))
    }
  }

  private isInGap(angleDeg: number): boolean {
    const normalized = ((angleDeg % 360) + 360) % 360
    for (const gap of PERIMETER_GAPS_DEG) {
      const center = ((gap.center % 360) + 360) % 360
      const diff = Math.min(
        Math.abs(normalized - center),
        360 - Math.abs(normalized - center),
      )
      if (diff < gap.halfWidth) return true
    }
    return false
  }

  private isTooCloseToExisting(
    x: number, z: number,
    points: Array<{ x: number; z: number }>,
    minDist: number,
  ): boolean {
    const minSq = minDist * minDist
    for (const p of points) {
      const dx = x - p.x
      const dz = z - p.z
      if (dx * dx + dz * dz < minSq) return true
    }
    return false
  }

  destroy(): void {
    for (const vb of this.vbs) vb.destroy()
    this.vbs = []
    if (this.root) {
      this.root.destroy()
      this.root = null
    }
  }
}
