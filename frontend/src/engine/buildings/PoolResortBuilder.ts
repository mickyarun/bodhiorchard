/**
 * PoolResortBuilder — Pool area with procedural water + beach loungers.
 *
 * Uses `buildBeachChair()` (procedural PlayCanvas primitives) for chairs
 * and `WaterSurface` for the pool. No GLB loading for chairs — the seat
 * height is a compile-time constant from ProceduralBeachChair.SEAT_HEIGHT.
 */
import * as pc from "playcanvas"
import type { Application } from "../core/Application"
import { BuildingFactory } from "./BuildingFactory"
import { buildBeachChair, SEAT_HEIGHT } from "./ProceduralBeachChair"
import type { AssetLoader } from "../assets/AssetLoader"
import type { MaterialFactory } from "../rendering/MaterialFactory"
import type { InteractionPoint } from "../characters/InteractionPoint"
import type { ExclusionZone } from "../utils/MathUtils"
import { WaterSurface } from "../effects/WaterSurface"

export interface PoolResortResult {
  entity: pc.Entity
  exclusionZone: ExclusionZone
  seats: InteractionPoint[]
  pondObstacle: { x: number; z: number; radius: number }
  waterSurface: WaterSurface
}

const POOL_WIDTH = 6
const POOL_DEPTH = 6

export class PoolResortBuilder {
  private materials: MaterialFactory | null

  constructor(factory: BuildingFactory, _loader: AssetLoader) {
    this.materials = factory.materialFactory
  }

  async build(
    app: Application,
    x: number,
    z: number,
  ): Promise<PoolResortResult> {
    const root = new pc.Entity("PoolResort")
    root.setPosition(x, 0, z)

    const seats: InteractionPoint[] = []
    let seatIndex = 0

    // ─── Procedural water body ───
    const waterSurface = new WaterSurface()
    waterSurface.build(app, this.materials!, {
      x, z,
      width: POOL_WIDTH,
      depth: POOL_DEPTH,
    })

    // ─── Procedural beach loungers around the pool ───
    const chairPositions: Array<{ lx: number; lz: number; yaw: number }> = [
      { lx: -5.0, lz: -1.5, yaw: 90 },
      { lx: -5.0, lz: 2.5,  yaw: 90 },
      { lx: 5.0,  lz: -1.5, yaw: -90 },
      { lx: 5.0,  lz: 2.5,  yaw: -90 },
      { lx: -2.5, lz: 5.0,  yaw: 180 },
      { lx: 2.5,  lz: 5.0,  yaw: 180 },
    ]

    for (const pos of chairPositions) {
      if (!this.materials) continue

      const chair = buildBeachChair(this.materials)
      chair.setLocalPosition(pos.lx, 0, pos.lz)
      chair.setLocalEulerAngles(0, pos.yaw, 0)
      root.addChild(chair)

      // InteractionSeat with known SEAT_HEIGHT — no SeatProber needed
      seats.push(BuildingFactory.createInteractionSeat(
        'pool_resort', seatIndex++,
        x + pos.lx, z + pos.lz,
        pos.yaw, 'poolChair', 'sit', 0, SEAT_HEIGHT,
      ))
    }

    app.root.addChild(root)

    return {
      entity: root,
      exclusionZone: { x, z, radius: 14 },
      seats,
      pondObstacle: { x, z, radius: POOL_WIDTH / 2 + 0.5 },
      waterSurface,
    }
  }
}
