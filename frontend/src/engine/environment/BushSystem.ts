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
 * BushSystem — Foliage bushes + decorative props along paths and open areas.
 *
 * Places bushes near path edges for a landscaped look, plus sparse
 * decorative props (stumps, logs, large rocks) in open grass areas
 * to fill the empty spaces between zones.
 *
 * Hardware-instanced: ~25 bushes + ~8 props collapse into one draw call
 * per (mesh, material) via buildInstancedGlbs instead of ~33 per-entity
 * matrix uploads. Bushes get the Theme leaf-green tint (cloned materials,
 * owned here); props keep their native GLB colors.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { AssetLoader } from '../assets/AssetLoader'
import { SCATTER_BUSHES, SCATTER_PROPS } from '../assets/AssetManifest'
import { isInsideAnyZone, randRange, type ExclusionZone } from '../utils/MathUtils'
import {
  buildInstancedGlbs, type GlbScatterGroup, type ScatterTransform,
} from '../utils/GlbInstancing'
import { Theme } from '../rendering/Theme'

const BUSH_COUNT = 25
const PROP_COUNT = 8
const WORLD_HALF = 40
const MIN_DISTANCE = 3.5

export class BushSystem {
  private root: pc.Entity | null = null
  private vbs: pc.VertexBuffer[] = []
  private materials: pc.Material[] = []

  async build(
    app: Application,
    loader: AssetLoader,
    exclusionZones: readonly ExclusionZone[],
    pathRoutes: Array<{ fromX: number; fromZ: number; toX: number; toZ: number }>,
  ): Promise<pc.Entity> {
    this.root = new pc.Entity('BushSystem')

    // Collect all placed points (shared between bushes + props for min distance)
    const allPoints: Array<{ x: number; z: number }> = []

    // 1. Bushes near paths (Quaternius models are ~2-4 units, scale down)
    const bushAssets = await loader.loadBatch(SCATTER_BUSHES)
    const bushGroups: GlbScatterGroup[] = bushAssets.map(
      (asset) => ({ asset, transforms: [] }),
    )
    const bushPoints = this.scatterNearPaths(
      BUSH_COUNT, pathRoutes, exclusionZones, allPoints,
    )
    for (const pt of bushPoints) {
      appendTransform(bushGroups, pt.x, pt.z, randRange(0.6, 1.3))
    }
    allPoints.push(...bushPoints)

    // 2. Decorative props (stumps, logs, rocks) in open areas
    const propAssets = await loader.loadBatch(SCATTER_PROPS)
    const propGroups: GlbScatterGroup[] = propAssets.map(
      (asset) => ({ asset, transforms: [] }),
    )
    for (const pt of this.scatterOpen(PROP_COUNT, exclusionZones, allPoints)) {
      appendTransform(propGroups, pt.x, pt.z, randRange(1.5, 3.0))
    }

    const bushes = buildInstancedGlbs(
      app.app.graphicsDevice, loader, bushGroups,
      { namePrefix: 'BushInstanced', tint: Theme.SCATTER.bush },
    )
    const props = buildInstancedGlbs(
      app.app.graphicsDevice, loader, propGroups,
      { namePrefix: 'PropInstanced' },
    )
    for (const e of [...bushes.entities, ...props.entities]) this.root.addChild(e)
    this.vbs = [...bushes.vbs, ...props.vbs]
    this.materials = [...bushes.materials, ...props.materials]

    app.root.addChild(this.root)
    return this.root
  }

  /** Scatter points near path routes (2-5 units offset from path line). */
  private scatterNearPaths(
    count: number,
    routes: Array<{ fromX: number; fromZ: number; toX: number; toZ: number }>,
    exclusionZones: readonly ExclusionZone[],
    existing: ReadonlyArray<{ x: number; z: number }>,
  ): Array<{ x: number; z: number }> {
    const points: Array<{ x: number; z: number }> = []
    const maxAttempts = count * 20
    let attempts = 0

    while (points.length < count && attempts < maxAttempts) {
      attempts++

      let x: number, z: number
      if (routes.length > 0 && Math.random() < 0.75) {
        const route = routes[Math.floor(Math.random() * routes.length)]
        const t = randRange(0.15, 0.85)
        const px = route.fromX + (route.toX - route.fromX) * t
        const pz = route.fromZ + (route.toZ - route.fromZ) * t
        const dx = route.toX - route.fromX
        const dz = route.toZ - route.fromZ
        const len = Math.sqrt(dx * dx + dz * dz) || 1
        const nx = -dz / len
        const nz = dx / len
        const offset = randRange(2, 5) * (Math.random() < 0.5 ? 1 : -1)
        x = px + nx * offset
        z = pz + nz * offset
      } else {
        x = randRange(-WORLD_HALF, WORLD_HALF)
        z = randRange(-WORLD_HALF, WORLD_HALF)
      }

      if (isInsideAnyZone(x, z, exclusionZones)) continue
      if (this.tooCloseToAny(x, z, points, existing)) continue

      points.push({ x, z })
    }

    return points
  }

  /** Scatter points in open grass areas (between zones, not near paths). */
  private scatterOpen(
    count: number,
    exclusionZones: readonly ExclusionZone[],
    existing: ReadonlyArray<{ x: number; z: number }>,
  ): Array<{ x: number; z: number }> {
    const points: Array<{ x: number; z: number }> = []
    const maxAttempts = count * 20
    let attempts = 0

    while (points.length < count && attempts < maxAttempts) {
      attempts++
      const x = randRange(-WORLD_HALF * 0.8, WORLD_HALF * 0.8)
      const z = randRange(-WORLD_HALF * 0.8, WORLD_HALF * 0.8)

      if (isInsideAnyZone(x, z, exclusionZones)) continue
      if (this.tooCloseToAny(x, z, points, existing)) continue

      points.push({ x, z })
    }

    return points
  }

  private tooCloseToAny(
    x: number, z: number,
    ...lists: readonly (ReadonlyArray<{ x: number; z: number }>)[]
  ): boolean {
    for (const list of lists) {
      for (const p of list) {
        const dx = x - p.x
        const dz = z - p.z
        if (dx * dx + dz * dz < MIN_DISTANCE * MIN_DISTANCE) return true
      }
    }
    return false
  }

  destroy(): void {
    for (const vb of this.vbs) vb.destroy()
    this.vbs = []
    for (const mat of this.materials) mat.destroy()
    this.materials = []
    if (this.root) {
      this.root.destroy()
      this.root = null
    }
  }
}

/** Append one yaw-randomized transform to a random group's bucket. */
function appendTransform(groups: GlbScatterGroup[], x: number, z: number, scale: number): void {
  const transform: ScatterTransform = {
    x, y: 0, z,
    yawDeg: randRange(0, 360),
    scale,
  }
  groups[Math.floor(Math.random() * groups.length)].transforms.push(transform)
}
