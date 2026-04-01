/**
 * PineTreeSystem — Pine/evergreen trees along the outer border ring.
 *
 * Places pine tree GLBs in a ring between the inner zone area and
 * the outer perimeter fence, creating a natural tree line border.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { AssetLoader } from '../assets/AssetLoader'
import { SCATTER_PINES } from '../assets/AssetManifest'
import { isInsideAnyZone, randRange, type ExclusionZone } from '../utils/MathUtils'

const PINE_COUNT = 40
const INNER_RADIUS = 45  // well past the perimeter fence
const OUTER_RADIUS = 80  // wide forest belt
const MIN_DISTANCE = 5.0

export class PineTreeSystem {
  private root: pc.Entity | null = null

  async build(
    app: Application,
    loader: AssetLoader,
    exclusionZones: readonly ExclusionZone[],
  ): Promise<pc.Entity> {
    this.root = new pc.Entity('PineTreeSystem')

    const pineAssets = await loader.loadBatch(SCATTER_PINES)

    const points = this.ringScatter(PINE_COUNT, MIN_DISTANCE, exclusionZones)
    for (const pt of points) {
      const asset = pineAssets[Math.floor(Math.random() * pineAssets.length)]
      const instance = loader.instance(asset)
      instance.setPosition(pt.x, 0, pt.z)
      instance.setLocalEulerAngles(0, randRange(0, 360), 0)
      const s = randRange(3, 7)
      instance.setLocalScale(s, s, s)
      this.root.addChild(instance)
    }

    app.root.addChild(this.root)
    return this.root
  }

  /** Scatter points in a ring between INNER_RADIUS and OUTER_RADIUS from origin. */
  private ringScatter(
    count: number,
    minDist: number,
    exclusionZones: readonly ExclusionZone[],
  ): Array<{ x: number; z: number }> {
    const points: Array<{ x: number; z: number }> = []
    const maxAttempts = count * 20
    let attempts = 0

    while (points.length < count && attempts < maxAttempts) {
      attempts++
      // Random angle + random radius within the ring
      const angle = Math.random() * Math.PI * 2
      const r = INNER_RADIUS + Math.random() * (OUTER_RADIUS - INNER_RADIUS)
      const x = Math.cos(angle) * r
      const z = Math.sin(angle) * r

      if (isInsideAnyZone(x, z, exclusionZones)) continue

      let tooClose = false
      for (const p of points) {
        const dx = x - p.x
        const dz = z - p.z
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
