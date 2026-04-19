// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * GrassSystem — Scattered GLB grass + flowers using Poisson disc sampling.
 *
 * Loads grass and flower GLBs from Kenney Nature Kit and scatters hundreds
 * of instances across the world, skipping exclusion zones (buildings, trees).
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { AssetLoader } from '../assets/AssetLoader'
import { SCATTER_GRASS, SCATTER_FLOWERS } from '../assets/AssetManifest'
import { isInsideAnyZone, randRange, type ExclusionZone } from '../utils/MathUtils'

const GRASS_COUNT = 450
const FLOWER_COUNT = 40
const WORLD_HALF = 40 // compact world with TILE_SIZE=1
const MIN_DISTANCE = 1.2 // tighter spacing for lush coverage

export class GrassSystem {
  private root: pc.Entity | null = null
  private grassAssets: pc.Asset[] = []
  private flowerAssets: pc.Asset[] = []

  async build(
    app: Application,
    loader: AssetLoader,
    exclusionZones: readonly ExclusionZone[],
  ): Promise<pc.Entity> {
    this.root = new pc.Entity('GrassSystem')

    // Load all grass + flower GLBs
    this.grassAssets = await loader.loadBatch(SCATTER_GRASS)
    this.flowerAssets = await loader.loadBatch(SCATTER_FLOWERS)

    // Scatter grass — scaled up for visibility
    const points = this.poissonScatter(GRASS_COUNT, WORLD_HALF, MIN_DISTANCE, exclusionZones)
    for (const pt of points) {
      const asset = this.grassAssets[Math.floor(Math.random() * this.grassAssets.length)]
      const instance = loader.instance(asset)
      instance.setPosition(pt.x, 0, pt.z)
      instance.setLocalEulerAngles(0, randRange(0, 360), 0)
      const s = randRange(1.5, 4.0) // wider variety — some tiny, some large
      instance.setLocalScale(s, s, s)
      this.root.addChild(instance)
    }

    // Scatter flowers (sparser, scaled up more — flowers are only ~0.16 units wide)
    const flowerPoints = this.poissonScatter(FLOWER_COUNT, WORLD_HALF, 3, exclusionZones)
    for (const pt of flowerPoints) {
      const asset = this.flowerAssets[Math.floor(Math.random() * this.flowerAssets.length)]
      const instance = loader.instance(asset)
      instance.setPosition(pt.x, 0, pt.z)
      instance.setLocalEulerAngles(0, randRange(0, 360), 0)
      const s = randRange(2.5, 5.5)
      instance.setLocalScale(s, s, s)
      this.root.addChild(instance)
    }

    app.root.addChild(this.root)
    return this.root
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

      // Skip exclusion zones
      if (isInsideAnyZone(x, z, exclusionZones as ExclusionZone[])) continue

      // Check minimum distance to existing points (limited check for speed)
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
    if (this.root) {
      this.root.destroy()
      this.root = null
    }
  }
}
