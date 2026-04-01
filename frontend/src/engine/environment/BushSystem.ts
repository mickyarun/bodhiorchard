/**
 * BushSystem — Foliage bushes + decorative props along paths and open areas.
 *
 * Places bushes near path edges for a landscaped look, plus sparse
 * decorative props (stumps, logs, large rocks) in open grass areas
 * to fill the empty spaces between zones.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { AssetLoader } from '../assets/AssetLoader'
import { SCATTER_BUSHES, SCATTER_PROPS } from '../assets/AssetManifest'
import { isInsideAnyZone, randRange, type ExclusionZone } from '../utils/MathUtils'

const BUSH_COUNT = 25
const PROP_COUNT = 8
const WORLD_HALF = 40
const MIN_DISTANCE = 3.5

export class BushSystem {
  private root: pc.Entity | null = null

  async build(
    app: Application,
    loader: AssetLoader,
    exclusionZones: readonly ExclusionZone[],
    pathRoutes: Array<{ fromX: number; fromZ: number; toX: number; toZ: number }>,
  ): Promise<pc.Entity> {
    this.root = new pc.Entity('BushSystem')

    // Collect all placed points (shared between bushes + props for min distance)
    const allPoints: Array<{ x: number; z: number }> = []

    // 1. Place bushes near paths (Quaternius models are ~2-4 units, scale down)
    const bushAssets = await loader.loadBatch(SCATTER_BUSHES)
    const bushPoints = this.scatterNearPaths(
      BUSH_COUNT, pathRoutes, exclusionZones, allPoints,
    )
    for (const pt of bushPoints) {
      const asset = bushAssets[Math.floor(Math.random() * bushAssets.length)]
      const instance = loader.instance(asset)
      instance.setPosition(pt.x, 0, pt.z)
      instance.setLocalEulerAngles(0, randRange(0, 360), 0)
      const s = randRange(0.6, 1.3)
      instance.setLocalScale(s, s, s)
      this.root.addChild(instance)
    }
    allPoints.push(...bushPoints)

    // 2. Place decorative props (stumps, logs, rocks) in open areas
    const propAssets = await loader.loadBatch(SCATTER_PROPS)
    const propPoints = this.scatterOpen(
      PROP_COUNT, exclusionZones, allPoints,
    )
    for (const pt of propPoints) {
      const asset = propAssets[Math.floor(Math.random() * propAssets.length)]
      const instance = loader.instance(asset)
      instance.setPosition(pt.x, 0, pt.z)
      instance.setLocalEulerAngles(0, randRange(0, 360), 0)
      const s = randRange(1.5, 3.0)
      instance.setLocalScale(s, s, s)
      this.root.addChild(instance)
    }

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
    if (this.root) {
      this.root.destroy()
      this.root = null
    }
  }
}
