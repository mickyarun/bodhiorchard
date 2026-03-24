/**
 * RockSystem — Scattered GLB rocks + stones.
 *
 * Sparser than grass — placed along zone borders, near paths, as decorative clusters.
 * Mix sizes: large rocks as landmarks, small stones as fill.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { AssetLoader } from '../assets/AssetLoader'
import { SCATTER_ROCKS } from '../assets/AssetManifest'
import { isInsideAnyZone, randRange, type ExclusionZone } from '../utils/MathUtils'

const ROCK_COUNT = 30
const WORLD_HALF = 40

export class RockSystem {
  private root: pc.Entity | null = null

  async build(
    app: Application,
    loader: AssetLoader,
    exclusionZones: readonly ExclusionZone[],
  ): Promise<pc.Entity> {
    this.root = new pc.Entity('RockSystem')

    const rockAssets = await loader.loadBatch(SCATTER_ROCKS)

    let placed = 0
    let attempts = 0
    const maxAttempts = ROCK_COUNT * 10

    while (placed < ROCK_COUNT && attempts < maxAttempts) {
      attempts++
      const x = randRange(-WORLD_HALF, WORLD_HALF)
      const z = randRange(-WORLD_HALF, WORLD_HALF)

      if (isInsideAnyZone(x, z, exclusionZones as ExclusionZone[])) continue

      const asset = rockAssets[Math.floor(Math.random() * rockAssets.length)]
      const instance = loader.instance(asset)
      instance.setPosition(x, 0, z)
      instance.setLocalEulerAngles(0, randRange(0, 360), 0)
      const s = randRange(2, 4) // rocks are ~0.26–1.0 units
      instance.setLocalScale(s, s, s)
      this.root.addChild(instance)
      placed++
    }

    app.root.addChild(this.root)
    return this.root
  }

  destroy(): void {
    if (this.root) {
      this.root.destroy()
      this.root = null
    }
  }
}
