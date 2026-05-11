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
 * GrassSystem — Scattered GLB grass + flowers using Poisson disc sampling.
 *
 * Loads grass and flower GLBs from Kenney Nature Kit and scatters hundreds
 * of instances across the world, skipping exclusion zones (buildings, trees).
 *
 * Hardware-instanced via `buildInstancedGlbs` so the 450 grass + 40 flower
 * scatter points collapse into ~6 draw calls (one per (mesh, material)
 * combination across the 3 grass + 3 flower GLBs) instead of 490 entities
 * each driving its own per-mesh transform upload.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { AssetLoader } from '../assets/AssetLoader'
import { SCATTER_GRASS, SCATTER_FLOWERS } from '../assets/AssetManifest'
import { isInsideAnyZone, randRange, type ExclusionZone } from '../utils/MathUtils'
import {
  buildInstancedGlbs, type GlbScatterGroup, type ScatterTransform,
} from '../utils/GlbInstancing'

const GRASS_COUNT = 450
const FLOWER_COUNT = 40
const WORLD_HALF = 40 // compact world with TILE_SIZE=1
const MIN_DISTANCE = 1.2 // tighter spacing for lush coverage

export class GrassSystem {
  private root: pc.Entity | null = null
  private vbs: pc.VertexBuffer[] = []

  async build(
    app: Application,
    loader: AssetLoader,
    exclusionZones: readonly ExclusionZone[],
  ): Promise<pc.Entity> {
    this.root = new pc.Entity('GrassSystem')

    const grassAssets = await loader.loadBatch(SCATTER_GRASS)
    const flowerAssets = await loader.loadBatch(SCATTER_FLOWERS)

    const grassGroups = this.scatterIntoAssetGroups(
      grassAssets, GRASS_COUNT, MIN_DISTANCE, 1.5, 4.0, exclusionZones,
    )
    const flowerGroups = this.scatterIntoAssetGroups(
      flowerAssets, FLOWER_COUNT, 3, 2.5, 5.5, exclusionZones,
    )

    const { entities, vbs } = buildInstancedGlbs(
      app.app.graphicsDevice,
      loader,
      [...grassGroups, ...flowerGroups],
      { namePrefix: 'GrassInstanced' },
    )
    for (const e of entities) this.root.addChild(e)
    this.vbs = vbs

    app.root.addChild(this.root)
    return this.root
  }

  /**
   * Scatter `count` points across the world (skipping exclusion zones) and
   * randomly bucket each point into one of the asset groups. Each bucket's
   * transforms list is what `buildInstancedGlbs` consumes to build a single
   * instanced batch per (mesh, material) for that asset.
   */
  private scatterIntoAssetGroups(
    assets: pc.Asset[],
    count: number,
    minDist: number,
    minScale: number,
    maxScale: number,
    exclusionZones: readonly ExclusionZone[],
  ): GlbScatterGroup[] {
    const groups: GlbScatterGroup[] = assets.map((asset) => ({
      asset, transforms: [],
    }))
    const points = this.poissonScatter(count, WORLD_HALF, minDist, exclusionZones)
    for (const pt of points) {
      const idx = Math.floor(Math.random() * assets.length)
      const transform: ScatterTransform = {
        x: pt.x, y: 0, z: pt.z,
        yawDeg: randRange(0, 360),
        scale:  randRange(minScale, maxScale),
      }
      groups[idx].transforms.push(transform)
    }
    return groups
  }

  /**
   * Simple Poisson-ish scatter: random rejection with minimum distance.
   * Not a true Poisson disc sample, but fast enough for decorative placement.
   */
  private poissonScatter(
    count: number,
    halfExtent: number,
    minDist: number,
    exclusionZones: readonly ExclusionZone[],
  ): Array<{ x: number; z: number }> {
    const points: Array<{ x: number; z: number }> = []
    const maxAttempts = count * 10
    let attempts = 0

    while (points.length < count && attempts < maxAttempts) {
      attempts++
      const x = randRange(-halfExtent, halfExtent)
      const z = randRange(-halfExtent, halfExtent)

      if (isInsideAnyZone(x, z, exclusionZones as ExclusionZone[])) continue

      let tooClose = false
      const checkCount = Math.min(points.length, 20)
      for (let i = points.length - checkCount; i < points.length; i++) {
        const dx = x - points[i].x
        const dz = z - points[i].z
        if (dx * dx + dz * dz < minDist * minDist) {
          tooClose = true
          break
        }
      }
      if (tooClose) continue

      points.push({ x, z })
    }

    return points
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
