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
 * SandRoadBuilder — shared sand-strip road + stepping stone system.
 *
 * Builds village roads (street strips, cross-connectors, driveways)
 * using a gradient sand texture and scattered stepping stones.
 *
 * Used by both ExteriorScene (housetest) and HousingVillage (production).
 * PathSystem uses a different noisy texture — intentionally separate.
 */
import * as pc from 'playcanvas'
import type { AssetLoader } from '../assets/AssetLoader'
import { PATH } from '../assets/AssetManifest'
import { getHouseTier } from '../buildings/HouseTierConfig'
import type { StreetDef, VillagePlacement } from '@shared/world/VillageLayout'
import { randRange } from '../utils/MathUtils'

// ─── Constants ──────────────────────────────────────

const STONE_SPACING = 1.8
const STONE_SCALE   = 1.5
const SAND_WIDTH    = 3.5
const SAND_TEX_SIZE = 128

// ─── Types ──────────────────────────────────────────

export interface RoadBuildOptions {
  /** Build short perpendicular driveways from street to each house door. */
  driveways?: boolean
}

// ─── SandRoadBuilder ────────────────────────────────

export class SandRoadBuilder {
  private loader: AssetLoader
  private sandMaterial: pc.StandardMaterial | null = null
  private sandTexture: pc.Texture | null = null
  private stoneAsset: pc.Asset | null = null

  constructor(loader: AssetLoader) {
    this.loader = loader
  }

  /** Create shared sand texture + material. Call before buildRoads(). */
  async init(): Promise<void> {
    this.sandTexture = this.createSandTexture()
    this.sandMaterial = new pc.StandardMaterial()
    this.sandMaterial.diffuseMap = this.sandTexture
    this.sandMaterial.diffuse = new pc.Color(1, 1, 1)
    this.sandMaterial.metalness = 0
    this.sandMaterial.gloss = 0.06
    this.sandMaterial.opacityMap = this.sandTexture
    this.sandMaterial.alphaTest = 0.01
    this.sandMaterial.blendType = pc.BLEND_NORMAL
    this.sandMaterial.depthWrite = false
    this.sandMaterial.cull = pc.CULLFACE_NONE
    this.sandMaterial.update()

    this.stoneAsset = await this.loader.load(PATH.stone)
  }

  /** Build all village roads: street strips, cross-connector, and optional driveways. */
  buildRoads(
    root: pc.Entity,
    streets: StreetDef[],
    placements: VillagePlacement[],
    options?: RoadBuildOptions,
  ): void {
    if (!this.sandMaterial || !this.stoneAsset) return

    const maxEndX = streets.length > 1 ? Math.max(...streets.map(s => s.endX)) + 2 : 0

    // Street roads (sand strips + stepping stones)
    for (const street of streets) {
      const effectiveEndX = streets.length > 1 ? maxEndX : street.endX
      const roadLen = effectiveEndX - street.startX
      const midX = (street.startX + effectiveEndX) / 2

      this.addSandStrip(root, midX, street.centerZ, roadLen, SAND_WIDTH, 0.015)
      this.addSteppingStones(root, street.startX, street.centerZ, roadLen, 0)
    }

    // Cross-street connector (east edge, linking parallel streets)
    if (streets.length > 1) {
      const connX = maxEndX + 2
      const firstZ = streets[0].centerZ
      const lastZ = streets[streets.length - 1].centerZ
      const connLen = lastZ - firstZ

      this.addSandStrip(root, connX, (firstZ + lastZ) / 2, SAND_WIDTH * 0.8, connLen + SAND_WIDTH, 0.014)
      this.addSteppingStones(root, connX, firstZ, connLen, 90)
    }

    // Driveways: short perpendicular paths from street to each house door
    if (options?.driveways) {
      this.buildDriveways(root, streets, placements)
    }
  }

  destroy(): void {
    this.sandMaterial?.destroy()
    this.sandTexture?.destroy()
    this.sandMaterial = null
    this.sandTexture = null
    this.stoneAsset = null
  }

  // ─── Private helpers ──────────────────────────────

  private buildDriveways(root: pc.Entity, streets: StreetDef[], placements: VillagePlacement[]): void {
    for (const p of placements) {
      const street = streets[p.streetIndex]
      if (!street) continue

      // Door offset from house center (both housetest and production use pivot pattern)
      const tierDef = getHouseTier(p.tier)
      let doorOffset: number
      if (tierDef.exteriorFootprint && tierDef.exteriorScale) {
        doorOffset = (tierDef.exteriorFootprint.d * tierDef.exteriorScale) / 2
      } else {
        doorOffset = tierDef.depth / 2
      }

      // Door is on the side facing the road
      const doorZ = p.side === 'north' ? p.z + doorOffset : p.z - doorOffset
      const fromZ = street.centerZ
      const driveLen = Math.abs(doorZ - fromZ)
      if (driveLen < 1) continue

      this.addSandStrip(root, p.x, (fromZ + doorZ) / 2, SAND_WIDTH * 0.5, driveLen, 0.013)

      // Stepping stones along driveway
      const driveSteps = Math.max(2, Math.floor(driveLen / STONE_SPACING))
      for (let i = 0; i <= driveSteps; i++) {
        const t = driveSteps === 0 ? 0.5 : i / driveSteps
        const sz = fromZ + t * (doorZ - fromZ)
        const stone = this.loader.instance(this.stoneAsset!)
        stone.setPosition(p.x + randRange(-0.1, 0.1), 0.02, sz)
        stone.setLocalEulerAngles(0, 90 + randRange(-10, 10), 0)
        const s = STONE_SCALE * 0.8 + randRange(-0.1, 0.1)
        stone.setLocalScale(s, s, s)
        root.addChild(stone)
      }
    }
  }

  private addSandStrip(root: pc.Entity, x: number, z: number, w: number, d: number, y: number): void {
    const strip = new pc.Entity('RoadStrip')
    strip.addComponent('render', { type: 'plane' })
    strip.setLocalScale(w, 1, d)
    strip.setPosition(x, y, z)
    strip.render!.meshInstances[0].material = this.sandMaterial!
    root.addChild(strip)
  }

  /** Scatter stepping stones along a line from (startX, startZ) for `length` units. */
  private addSteppingStones(root: pc.Entity, startX: number, startZ: number, length: number, baseYaw: number): void {
    const steps = Math.floor(length / STONE_SPACING)
    const isVertical = baseYaw === 90
    for (let i = 0; i <= steps; i++) {
      const t = steps === 0 ? 0.5 : i / steps
      const stone = this.loader.instance(this.stoneAsset!)
      if (isVertical) {
        stone.setPosition(startX + randRange(-0.2, 0.2), 0.02, startZ + t * length)
      } else {
        stone.setPosition(startX + t * length + randRange(-0.15, 0.15), 0.02, startZ + randRange(-0.3, 0.3))
      }
      stone.setLocalEulerAngles(0, baseYaw + randRange(-10, 10), 0)
      const s = STONE_SCALE + randRange(-0.2, 0.2)
      stone.setLocalScale(s, s, s)
      root.addChild(stone)
    }
  }

  /** Procedural gradient sand texture with soft alpha edges. */
  private createSandTexture(): pc.Texture {
    const canvas = document.createElement('canvas')
    canvas.width = SAND_TEX_SIZE
    canvas.height = SAND_TEX_SIZE
    const ctx = canvas.getContext('2d')!

    const grad = ctx.createRadialGradient(
      SAND_TEX_SIZE / 2, SAND_TEX_SIZE / 2, 0,
      SAND_TEX_SIZE / 2, SAND_TEX_SIZE / 2, SAND_TEX_SIZE / 2,
    )
    grad.addColorStop(0, 'rgba(210, 190, 150, 0.9)')
    grad.addColorStop(0.6, 'rgba(200, 180, 140, 0.7)')
    grad.addColorStop(1, 'rgba(180, 165, 120, 0.0)')

    ctx.fillStyle = grad
    ctx.fillRect(0, 0, SAND_TEX_SIZE, SAND_TEX_SIZE)

    const texture = new pc.Texture(this.loader.app.graphicsDevice, {
      width: SAND_TEX_SIZE,
      height: SAND_TEX_SIZE,
      format: pc.PIXELFORMAT_RGBA8,
      minFilter: pc.FILTER_LINEAR,
      magFilter: pc.FILTER_LINEAR,
    })
    const pixels = texture.lock()
    pixels.set(ctx.getImageData(0, 0, SAND_TEX_SIZE, SAND_TEX_SIZE).data)
    texture.unlock()
    return texture
  }
}
