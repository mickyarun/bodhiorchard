/**
 * PoolScene — Pool resort test scene with SeatProber-based chair seating.
 *
 * Places 6 umbrella+chair sets around a ground plane. Unlike the production
 * PoolResortBuilder (which uses hardcoded seat heights), this scene uses
 * SeatProber.probeSeatY() to detect the actual chair cushion surface from
 * mesh geometry — the same approach used by all other buildings.
 *
 * The detected seatY is logged to console so it can be used to calibrate
 * the production SEAT_OFFSETS and server BreakSeatGenerator.
 */
import * as pc from 'playcanvas'
import type { AssetLoader } from '../assets/AssetLoader'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import { POOL } from '../assets/AssetManifest'
import { SeatProber } from '../characters/SeatProber'
import { POOL_CHAIRS, type PoolChairDef } from './SceneConfig'
import { InteractableItem } from './InteractableItem'

/** Model-space constants for the umbrella+chairs GLB (same as PoolResortBuilder). */
const UC_NATIVE_WIDTH = 361.25
const UC_CENTER_X = -20.74
const UC_CENTER_Z = 32.28
const UC_Y_MIN = -218.68
const UC_TARGET_WIDTH = 2.5
const UC_SCALE = UC_TARGET_WIDTH / UC_NATIVE_WIDTH

export interface PoolChairResult {
  def: PoolChairDef
  wrapper: pc.Entity
  /** SeatProber-detected seat surface Y, or null if detection failed. */
  probedSeatY: number | null
  /** Final seat world position (x, y, z) + yaw for the character. */
  seatWorldX: number
  seatWorldY: number
  seatWorldZ: number
  seatYaw: number
}

export class PoolScene {
  private loader: AssetLoader
  private materials: MaterialFactory | null
  private chairResults: PoolChairResult[] = []

  /** Interactable items — one per chair, for E-key sit interaction. */
  readonly items: InteractableItem[] = []

  constructor(loader: AssetLoader, materials: MaterialFactory | null) {
    this.loader = loader
    this.materials = materials
  }

  async build(root: pc.Entity): Promise<void> {
    // Ground plane
    const ground = new pc.Entity('PoolGround')
    ground.addComponent('render', { type: 'plane' })
    ground.setLocalScale(30, 1, 30)
    if (this.materials) {
      ground.render!.meshInstances[0].material =
        this.materials.getColor('pool_ground', 0.35, 0.55, 0.25)
    }
    root.addChild(ground)

    // Simple pool water placeholder (flat blue plane)
    const water = new pc.Entity('PoolWater')
    water.addComponent('render', { type: 'plane' })
    water.setLocalScale(6, 1, 6)
    water.setPosition(0, 0.05, 0)
    if (this.materials) {
      water.render!.meshInstances[0].material =
        this.materials.getColor('pool_water', 0.2, 0.5, 0.8, { emissive: [0.1, 0.25, 0.4] })
    }
    root.addChild(water)

    // Load umbrella+chair asset
    const ucAsset = await this.loader.load(POOL.umbrellaChairs)

    // Place each chair and probe its seat surface
    for (const chairDef of POOL_CHAIRS) {
      const result = this.placeChairWithProbing(root, ucAsset, chairDef)
      this.chairResults.push(result)

      // Create interactable for E-key sit
      const item = new InteractableItem(
        chairDef.id,
        new pc.Vec3(chairDef.x, 0, chairDef.z),
        '[E] Sit in lounge chair',
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
   * Place an umbrella+chair set and use SeatProber to detect the seat surface.
   * Uses the same model-space centering as PoolResortBuilder.placeUmbrellaSet(),
   * then calls SeatProber.probeSeatY() on the wrapper entity.
   */
  private placeChairWithProbing(
    parent: pc.Entity,
    ucAsset: pc.Asset,
    def: PoolChairDef,
  ): PoolChairResult {
    // Instance the model
    const model = this.loader.instance(ucAsset)
    model.setLocalScale(UC_SCALE, UC_SCALE, UC_SCALE)
    model.setLocalPosition(
      -UC_CENTER_X * UC_SCALE,
      -UC_Y_MIN * UC_SCALE,
      -UC_CENTER_Z * UC_SCALE,
    )

    // Wrapper for centering + rotation
    const wrapper = new pc.Entity(`PoolChair_${def.id}`)
    wrapper.addChild(model)
    wrapper.setLocalPosition(def.x, 0, def.z)
    if (def.yaw !== 0) wrapper.setLocalEulerAngles(0, def.yaw, 0)
    parent.addChild(wrapper)

    // Probe seat surface Y from actual mesh geometry
    const probedSeatY = SeatProber.probeSeatY(wrapper)

    // Fallback to the SEAT_OFFSETS value if probing fails
    const FALLBACK_SEAT_Y = 0.47
    const seatY = probedSeatY ?? FALLBACK_SEAT_Y

    // Compute seat world position — apply forward offset along yaw direction
    const FORWARD_OFFSET = 0.15
    const yawRad = (def.yaw * Math.PI) / 180
    const fwdX = Math.sin(yawRad) * FORWARD_OFFSET
    const fwdZ = Math.cos(yawRad) * FORWARD_OFFSET

    return {
      def,
      wrapper,
      probedSeatY,
      seatWorldX: def.x + fwdX,
      seatWorldY: seatY,
      seatWorldZ: def.z + fwdZ,
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
