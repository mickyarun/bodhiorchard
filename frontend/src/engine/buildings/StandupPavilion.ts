/**
 * StandupPavilion — Open circular meeting area with benches.
 *
 * Circular pavilion with fence perimeter, cushioned benches facing center,
 * stone path floor, and a campfire/log as gathering focal point.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { BuildingFactory } from './BuildingFactory'
import { AssetLoader } from '../assets/AssetLoader'
import { PAVILION, CAMPFIRE, BUILDING } from '../assets/AssetManifest'
import type { InteractionPoint } from '../characters/InteractionPoint'
import type { ExclusionZone } from '../utils/MathUtils'

export interface PavilionResult {
  entity: pc.Entity
  exclusionZone: ExclusionZone
  seats: InteractionPoint[]
}

const BENCH_COUNT = 6
const PAVILION_RADIUS = 5

export class StandupPavilion {
  private factory: BuildingFactory

  constructor(loader: AssetLoader) {
    this.factory = new BuildingFactory(loader)
  }

  async build(app: Application, x: number, z: number): Promise<PavilionResult> {
    const root = new pc.Entity('StandupPavilion')
    root.setPosition(x, 0, z)

    const seats: InteractionPoint[] = []

    // Fence perimeter
    const fenceCount = 10
    for (let i = 0; i < fenceCount; i++) {
      const angle = (i / fenceCount) * Math.PI * 2
      const fx = Math.cos(angle) * PAVILION_RADIUS
      const fz = Math.sin(angle) * PAVILION_RADIUS
      const yaw = -(angle * 180) / Math.PI + 90
      await this.factory.placeFurniture(root, PAVILION.fence, fx, 0, fz, yaw)
    }

    // Stone path floor (center area)
    for (let dx = -1; dx <= 1; dx++) {
      for (let dz = -1; dz <= 1; dz++) {
        await this.factory.placeFurniture(root, PAVILION.pathStone, dx * 1.5, 0, dz * 1.5)
      }
    }

    // Benches facing center — after AABB centering, front faces +Z,
    // so yaw = -90 - θ°  makes +Z point toward (0,0) from position at angle θ
    for (let i = 0; i < BENCH_COUNT; i++) {
      const angle = (i / BENCH_COUNT) * Math.PI * 2
      const bx = Math.cos(angle) * (PAVILION_RADIUS * 0.6)
      const bz = Math.sin(angle) * (PAVILION_RADIUS * 0.6)
      const yaw = -90 - (angle * 180) / Math.PI

      const bench = await this.factory.placeSeat(root, BUILDING.benchCushion, bx, bz, yaw, 'pavilion', i, x, z, 'pavilionBench')
      seats.push(bench.seat)
    }

    // Campfire in center
    await this.factory.placeFurniture(root, CAMPFIRE.stones, 0, 0, 0)
    await this.factory.placeFurniture(root, CAMPFIRE.logs, 0, 0.1, 0)

    app.root.addChild(root)

    return {
      entity: root,
      exclusionZone: { x, z, radius: PAVILION_RADIUS + 5 },
      seats,
    }
  }
}
