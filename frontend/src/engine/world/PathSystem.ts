/**
 * PathSystem — Stone paths connecting zone centers.
 *
 * Places path_stone GLBs at regular intervals along straight lines
 * from the orchard center to each building zone. Each stone is slightly
 * rotated for a natural, hand-placed feel.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { AssetLoader } from '../assets/AssetLoader'
import { randRange } from '../utils/MathUtils'

const PATH_ASSET = 'assets/garden/path_stone.glb'
const STONE_SPACING = 1.8 // world units between stones
const STONE_SCALE = 1.5   // path stones are ~1 unit, scale up slightly

interface PathRoute {
  fromX: number
  fromZ: number
  toX: number
  toZ: number
}

export class PathSystem {
  private root: pc.Entity | null = null

  async build(
    app: Application,
    loader: AssetLoader,
    routes: PathRoute[],
  ): Promise<pc.Entity> {
    this.root = new pc.Entity('PathSystem')

    const asset = await loader.load(PATH_ASSET)

    for (const route of routes) {
      const dx = route.toX - route.fromX
      const dz = route.toZ - route.fromZ
      const dist = Math.sqrt(dx * dx + dz * dz)
      const steps = Math.floor(dist / STONE_SPACING)

      if (steps < 2) continue

      const nx = dx / dist
      const nz = dz / dist
      // Path angle for aligning stones perpendicular to path direction
      const pathAngle = Math.atan2(nx, nz) * (180 / Math.PI)

      for (let i = 1; i < steps; i++) {
        const t = i / steps
        const sx = route.fromX + dx * t + randRange(-0.15, 0.15)
        const sz = route.fromZ + dz * t + randRange(-0.15, 0.15)

        const stone = loader.instance(asset)
        stone.setPosition(sx, 0.01, sz) // slightly above ground to avoid z-fight
        stone.setLocalEulerAngles(0, pathAngle + randRange(-10, 10), 0)
        const s = STONE_SCALE + randRange(-0.2, 0.2)
        stone.setLocalScale(s, s, s)
        this.root.addChild(stone)
      }
    }

    app.root.addChild(this.root)
    return this.root
  }

  /** Generate default routes from orchard center to each building zone. */
  static defaultRoutes(zones: Array<{ name: string; x: number; z: number }>): PathRoute[] {
    const routes: PathRoute[] = []
    const orchard = zones.find(z => z.name === 'orchard')
    if (!orchard) return routes

    for (const zone of zones) {
      if (zone.name === 'orchard') continue
      routes.push({
        fromX: orchard.x,
        fromZ: orchard.z,
        toX: zone.x,
        toZ: zone.z,
      })
    }

    return routes
  }

  destroy(): void {
    if (this.root) {
      this.root.destroy()
      this.root = null
    }
  }
}
