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
 * GrassSystem — a dense painterly grass CARPET with flower tufts.
 *
 * The old version scattered ~700 isolated tufts that read as bright
 * clumps stuck on the ground texture. The carpet look needs density and
 * color harmony instead: ~30k low blade tufts on a jittered grid, roots
 * at the ground color, split across three subtly-tinted batches so the
 * field has large-scale patch variation. Three instanced draw calls
 * total for the grass, three more for the flower color groups.
 *
 * Placement skips exclusion zones AND a rasterized path-clearance grid
 * (blades poking through the path strips break the illusion fastest).
 *
 * All foliage materials take the GrassWind transformVS sway.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import type { AssetLoader } from '../assets/AssetLoader'
import { isInsideAnyZone, randRange, type ExclusionZone } from '../utils/MathUtils'
import { evalRouteAt, type PathRoute } from '@shared/world/paths'
import { createInstancedEntity, computeInstanceAabb } from '../treetest/instancing'
import { Theme } from '../rendering/Theme'
import { GrassWind } from '../effects/GrassWind'
import {
  buildBladeTexture,
  buildCrossQuadMesh,
  buildFlowerTexture,
  buildFoliageMaterial,
} from './GrassAssets'

// ─── Carpet density ──────────────────────────────────────────────────────
const CARPET_HALF = 58       // world half-extent the carpet covers
const GRID_STEP = 0.55       // jittered-grid spacing → ~33k candidate points
const DROPOUT = 0.22         // random gaps keep the grid from reading as a grid
const TUFT_WIDTH = 1.05
const TUFT_HEIGHT = 0.55

// ─── Flowers ─────────────────────────────────────────────────────────────
const FLOWER_COUNT = 240
const FLOWER_MIN_DIST = 2.4
const FLOWER_WIDTH = 0.55
const FLOWER_HEIGHT = 0.7

/** Keep blades off the walking strips (primary path half-width ≈1.5). */
const PATH_CLEARANCE = 2.2
const PATH_SAMPLES_PER_ROUTE = 28
const CELL = 1.0

/** A rotated rectangle the carpet must stay out of (e.g. the village
 *  compound — blades grow up to the fence, none inside). */
export interface BlockedRect {
  cx: number
  cz: number
  yawRad: number
  halfW: number
  halfD: number
}

function insideAnyRect(x: number, z: number, rects: readonly BlockedRect[]): boolean {
  for (const r of rects) {
    const dx = x - r.cx
    const dz = z - r.cz
    // World → rect-local, matching HousingVillage.computeGateSide's
    // convention exactly (same yaw sign, same axes).
    const cos = Math.cos(r.yawRad)
    const sin = Math.sin(r.yawRad)
    const lx = dx * cos - dz * sin
    const lz = dx * sin + dz * cos
    if (Math.abs(lx) <= r.halfW && Math.abs(lz) <= r.halfD) return true
  }
  return false
}

export class GrassSystem {
  private root: pc.Entity | null = null
  private vbs: pc.VertexBuffer[] = []
  private materials: pc.Material[] = []
  private meshes: pc.Mesh[] = []
  private textures: pc.Texture[] = []
  private wind = new GrassWind()

  async build(
    app: Application,
    _loader: AssetLoader,
    exclusionZones: readonly ExclusionZone[],
    pathRoutes: readonly PathRoute[] = [],
    blockedRects: readonly BlockedRect[] = [],
  ): Promise<pc.Entity> {
    this.root = new pc.Entity('GrassSystem')
    const device = app.app.graphicsDevice
    const blockedCells = this.rasterizePathClearance(pathRoutes)

    // A circular zone whose center sits inside a blocked rect is the
    // rect's own (oversized) exclusion circle — drop it so blades grow
    // right up to the rect edge (the fence) instead of stopping at the
    // circle and leaving a bald ring of bare ground texture around it.
    const zones = exclusionZones.filter(
      (z) => !insideAnyRect(z.x, z.z, blockedRects),
    )

    this.buildCarpet(device, zones, blockedCells, blockedRects)
    this.buildFlowers(device, zones, blockedCells, blockedRects)

    app.root.addChild(this.root)
    return this.root
  }

  /** Advance the wind clock — call once per frame. */
  update(dt: number): void {
    this.wind.update(dt)
  }

  /** ~30k blade tufts in three subtly-tinted instanced batches. */
  private buildCarpet(
    device: pc.GraphicsDevice,
    exclusionZones: readonly ExclusionZone[],
    blockedCells: Set<string>,
    blockedRects: readonly BlockedRect[],
  ): void {
    const bladeTexture = buildBladeTexture(device)
    this.textures.push(bladeTexture)
    const mesh = buildCrossQuadMesh(device, TUFT_WIDTH, TUFT_HEIGHT)
    this.meshes.push(mesh)

    const tints = Theme.GRASS_BLADES.batchTints
    const batches: number[][] = tints.map(() => [])

    const mat = new pc.Mat4()
    const pos = new pc.Vec3()
    const rot = new pc.Quat()
    const scl = new pc.Vec3()
    for (let gx = -CARPET_HALF; gx <= CARPET_HALF; gx += GRID_STEP) {
      for (let gz = -CARPET_HALF; gz <= CARPET_HALF; gz += GRID_STEP) {
        if (Math.random() < DROPOUT) continue
        // Full-cell jitter — anything less leaves faint concentric row
        // artifacts readable at the overview zoom.
        const x = gx + randRange(-GRID_STEP, GRID_STEP) * 0.5
        const z = gz + randRange(-GRID_STEP, GRID_STEP) * 0.5
        if (isInsideAnyZone(x, z, exclusionZones as ExclusionZone[])) continue
        if (blockedCells.has(this.cellKey(x, z))) continue
        if (insideAnyRect(x, z, blockedRects)) continue

        pos.set(x, 0, z)
        rot.setFromEulerAngles(0, randRange(0, 360), 0)
        const s = randRange(0.75, 1.25)
        scl.set(s, s * randRange(0.8, 1.35), s)
        mat.setTRS(pos, rot, scl)
        const bucket = batches[Math.floor(Math.random() * batches.length)]
        for (let k = 0; k < 16; k++) bucket.push(mat.data[k])
      }
    }

    for (let i = 0; i < batches.length; i++) {
      const flat = batches[i]
      const count = flat.length / 16
      if (count === 0) continue
      const material = buildFoliageMaterial(bladeTexture)
      const [tr, tg, tb] = tints[i]
      material.diffuse = new pc.Color(tr, tg, tb)
      material.update()
      this.materials.push(material)

      const matrices = new Float32Array(flat)
      const aabb = computeInstanceAabb(matrices, count, TUFT_HEIGHT * 2)
      const { entity, vb } = createInstancedEntity(
        device, mesh, material, matrices, count, `GrassCarpet_${i}`, { aabb },
      )
      this.root!.addChild(entity)
      this.vbs.push(vb)
    }
    this.wind.apply(this.materials.slice(), Theme.SCATTER.grassWindStrength)
  }

  /** Flower tufts dotted through the carpet — one batch per petal color. */
  private buildFlowers(
    device: pc.GraphicsDevice,
    exclusionZones: readonly ExclusionZone[],
    blockedCells: Set<string>,
    blockedRects: readonly BlockedRect[],
  ): void {
    const mesh = buildCrossQuadMesh(device, FLOWER_WIDTH, FLOWER_HEIGHT)
    this.meshes.push(mesh)

    const petals = Theme.FLOWERS.petals
    const batches: number[][] = petals.map(() => [])
    const placed: Array<{ x: number; z: number }> = []
    const mat = new pc.Mat4()
    const pos = new pc.Vec3()
    const rot = new pc.Quat()
    const scl = new pc.Vec3()
    let attempts = 0
    while (placed.length < FLOWER_COUNT && attempts < FLOWER_COUNT * 12) {
      attempts++
      const x = randRange(-CARPET_HALF, CARPET_HALF)
      const z = randRange(-CARPET_HALF, CARPET_HALF)
      if (isInsideAnyZone(x, z, exclusionZones as ExclusionZone[])) continue
      if (blockedCells.has(this.cellKey(x, z))) continue
      if (insideAnyRect(x, z, blockedRects)) continue
      const minSq = FLOWER_MIN_DIST * FLOWER_MIN_DIST
      if (placed.some((p) => (p.x - x) ** 2 + (p.z - z) ** 2 < minSq)) continue
      placed.push({ x, z })

      pos.set(x, 0, z)
      rot.setFromEulerAngles(0, randRange(0, 360), 0)
      const s = randRange(0.8, 1.3)
      scl.set(s, s, s)
      mat.setTRS(pos, rot, scl)
      const bucket = batches[Math.floor(Math.random() * batches.length)]
      for (let k = 0; k < 16; k++) bucket.push(mat.data[k])
    }

    const flowerMats: pc.Material[] = []
    for (let i = 0; i < batches.length; i++) {
      const flat = batches[i]
      const count = flat.length / 16
      if (count === 0) continue
      const texture = buildFlowerTexture(device, petals[i])
      this.textures.push(texture)
      const material = buildFoliageMaterial(texture)
      this.materials.push(material)
      flowerMats.push(material)

      const matrices = new Float32Array(flat)
      const aabb = computeInstanceAabb(matrices, count, FLOWER_HEIGHT * 2)
      const { entity, vb } = createInstancedEntity(
        device, mesh, material, matrices, count, `GrassFlowers_${i}`, { aabb },
      )
      this.root!.addChild(entity)
      this.vbs.push(vb)
    }
    this.wind.apply(flowerMats, Theme.SCATTER.grassWindStrength * 0.7)
  }

  /** Mark CELL-sized cells within PATH_CLEARANCE of any primary-path sample
   *  so the per-point check is a single Set lookup, not a distance scan. */
  private rasterizePathClearance(routes: readonly PathRoute[]): Set<string> {
    const blocked = new Set<string>()
    const reach = Math.ceil(PATH_CLEARANCE / CELL)
    for (const route of routes) {
      for (let i = 0; i <= PATH_SAMPLES_PER_ROUTE; i++) {
        const p = evalRouteAt(route, i / PATH_SAMPLES_PER_ROUTE)
        const cx = Math.round(p.x / CELL)
        const cz = Math.round(p.z / CELL)
        for (let dx = -reach; dx <= reach; dx++) {
          for (let dz = -reach; dz <= reach; dz++) {
            blocked.add(`${cx + dx}:${cz + dz}`)
          }
        }
      }
    }
    return blocked
  }

  private cellKey(x: number, z: number): string {
    return `${Math.round(x / CELL)}:${Math.round(z / CELL)}`
  }

  destroy(): void {
    this.wind.clear()
    for (const vb of this.vbs) vb.destroy()
    this.vbs = []
    for (const material of this.materials) material.destroy()
    this.materials = []
    for (const mesh of this.meshes) {
      mesh.vertexBuffer?.destroy()
      mesh.indexBuffer?.[0]?.destroy()
    }
    this.meshes = []
    for (const texture of this.textures) texture.destroy()
    this.textures = []
    if (this.root) {
      this.root.destroy()
      this.root = null
    }
  }
}
