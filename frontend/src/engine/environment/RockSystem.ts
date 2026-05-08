// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * RockSystem — Scattered GLB rocks + stones.
 *
 * Sparser than grass — placed along zone borders, near paths, as decorative clusters.
 * Mix sizes: large rocks as landmarks, small stones as fill.
 *
 * Hardware-instanced: 30 scatter points across 9 rock GLBs collapse into
 * one draw call per (mesh, material) (≈9 draws total) instead of 30 per-entity
 * matrix uploads.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { AssetLoader } from '../assets/AssetLoader'
import { SCATTER_ROCKS } from '../assets/AssetManifest'
import { isInsideAnyZone, randRange, type ExclusionZone } from '../utils/MathUtils'
import {
  buildInstancedGlbs, type GlbScatterGroup, type ScatterTransform,
} from '../utils/GlbInstancing'

const ROCK_COUNT = 30
const WORLD_HALF = 40

export class RockSystem {
  private root: pc.Entity | null = null
  private vbs: pc.VertexBuffer[] = []

  async build(
    app: Application,
    loader: AssetLoader,
    exclusionZones: readonly ExclusionZone[],
  ): Promise<pc.Entity> {
    this.root = new pc.Entity('RockSystem')

    const rockAssets = await loader.loadBatch(SCATTER_ROCKS)
    const groups: GlbScatterGroup[] = rockAssets.map((asset) => ({
      asset, transforms: [],
    }))

    let placed = 0
    let attempts = 0
    const maxAttempts = ROCK_COUNT * 10

    while (placed < ROCK_COUNT && attempts < maxAttempts) {
      attempts++
      const x = randRange(-WORLD_HALF, WORLD_HALF)
      const z = randRange(-WORLD_HALF, WORLD_HALF)

      if (isInsideAnyZone(x, z, exclusionZones as ExclusionZone[])) continue

      const idx = Math.floor(Math.random() * rockAssets.length)
      const transform: ScatterTransform = {
        x, y: 0, z,
        yawDeg: randRange(0, 360),
        scale:  randRange(2, 4), // rocks are ~0.26–1.0 units
      }
      groups[idx].transforms.push(transform)
      placed++
    }

    const { entities, vbs } = buildInstancedGlbs(
      app.app.graphicsDevice,
      loader,
      groups,
      { namePrefix: 'RockInstanced' },
    )
    for (const e of entities) this.root.addChild(e)
    this.vbs = vbs

    app.root.addChild(this.root)
    return this.root
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
