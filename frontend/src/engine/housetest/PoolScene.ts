/**
 * PoolScene — Pool resort test scene with individual deck chairs.
 *
 * Places 6 individual `deck_chair.glb` chairs around a central pool.
 * Uses `placeFurnitureCentered`-style AABB centering + SeatProber to
 * detect the exact chair seat surface, then creates InteractableItems
 * for E-key sit interaction.
 *
 * This scene serves as the test harness for calibrating production
 * PoolResortBuilder's seat positions. The SeatProber results logged
 * to console should match the `deckChair` entry in SEAT_OFFSETS.
 */
import * as pc from 'playcanvas'
import type { AssetLoader } from '../assets/AssetLoader'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import { BuildingFactory } from '../buildings/BuildingFactory'
import { POOL } from '../assets/AssetManifest'
import { SeatProber } from '../characters/SeatProber'
import { POOL_CHAIRS, type PoolChairDef } from './SceneConfig'
import { InteractableItem } from './InteractableItem'

export interface PoolChairResult {
  def: PoolChairDef
  entity: pc.Entity
  /** SeatProber-detected seat surface Y, or null if detection failed. */
  probedSeatY: number | null
  /** Final seat world position (x, y, z) + yaw for the character. */
  seatWorldX: number
  seatWorldY: number
  seatWorldZ: number
  seatYaw: number
}

export class PoolScene {
  private factory: BuildingFactory
  private chairResults: PoolChairResult[] = []

  /** Interactable items — one per chair, for E-key sit interaction. */
  readonly items: InteractableItem[] = []

  constructor(loader: AssetLoader, materials: MaterialFactory | null) {
    this.factory = new BuildingFactory(loader, materials ?? undefined)
  }

  async build(root: pc.Entity): Promise<void> {
    // Ground plane
    const ground = new pc.Entity('PoolGround')
    ground.addComponent('render', { type: 'plane' })
    ground.setLocalScale(30, 1, 30)
    const matFactory = this.factory.materialFactory
    if (matFactory) {
      ground.render!.meshInstances[0].material =
        matFactory.getColor('pool_ground', 0.35, 0.55, 0.25)
    }
    root.addChild(ground)

    // Simple pool water placeholder (flat blue plane)
    const water = new pc.Entity('PoolWater')
    water.addComponent('render', { type: 'plane' })
    water.setLocalScale(6, 1, 6)
    water.setPosition(0, 0.05, 0)
    if (matFactory) {
      water.render!.meshInstances[0].material =
        matFactory.getColor('pool_water', 0.2, 0.5, 0.8, { emissive: [0.1, 0.25, 0.4] })
    }
    root.addChild(water)

    // Place each deck chair using placeFurnitureCentered + SeatProber
    for (const chairDef of POOL_CHAIRS) {
      const result = await this.placeChairWithProbing(root, chairDef)
      this.chairResults.push(result)

      // Create interactable for E-key sit
      const item = new InteractableItem(
        chairDef.id,
        new pc.Vec3(result.seatWorldX, 0, result.seatWorldZ),
        '[E] Sit in deck chair',
        `Relaxing... (seatY=${result.probedSeatY?.toFixed(3) ?? 'fallback'})`,
        'sit',
        {
          x: result.seatWorldX,
          z: result.seatWorldZ,
          yaw: chairDef.yaw,
          y: result.seatWorldY,
        },
        2.0, // proximity radius
      )
      this.items.push(item)
    }

    // Log all probed values for calibration
    console.log('[PoolScene] SeatProber results:')
    for (const r of this.chairResults) {
      console.log(
        `  ${r.def.id}: probedSeatY=${r.probedSeatY?.toFixed(4) ?? 'null'}, ` +
        `worldY=${r.seatWorldY.toFixed(4)}, pos=(${r.seatWorldX.toFixed(2)}, ${r.seatWorldZ.toFixed(2)})`,
      )
    }
  }

  /**
   * Place an individual deck chair using placeFurnitureCentered (AABB-centered)
   * and probe its seat surface with SeatProber.
   *
   * This is the same approach used by CoffeeBarBuilder/CafeteriaBuilder —
   * the chair is a single-entity GLB so SeatProber detects the actual chair
   * seat surface, not the center of a composite umbrella+chairs model.
   */
  private async placeChairWithProbing(
    parent: pc.Entity,
    def: PoolChairDef,
  ): Promise<PoolChairResult> {
    // Place using AABB centering (same as BuildingFactory.placeFurnitureCentered)
    const entity = await this.factory.placeFurnitureCentered(
      parent, POOL.deckChair, def.x, 0, def.z, def.yaw,
    )

    // Probe seat surface Y from actual mesh geometry — same approach as
    // the house interior's lounge chair / desk chair sitting.
    const probedSeatY = SeatProber.probeSeatY(entity)
    const seatY = probedSeatY ?? 0.20

    // Seat position = EXACT placement coords (same pattern as house interior:
    // the seat position matches the placeFurnitureCentered coordinates, no
    // forward offset or mesh-center math needed. AABB centering already puts
    // the model's visual center at def.x/def.z).
    return {
      def,
      entity,
      probedSeatY,
      seatWorldX: def.x,
      seatWorldY: seatY,
      seatWorldZ: def.z,
      seatYaw: def.yaw,
    }
  }

  /** Get the average probed seatY for calibrating production code. */
  getAverageProbedSeatY(): number | null {
    const probed = this.chairResults
      .map(r => r.probedSeatY)
      .filter((y): y is number => y !== null)
    if (probed.length === 0) return null
    return probed.reduce((sum, y) => sum + y, 0) / probed.length
  }
}
