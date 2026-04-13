/**
 * PoolScene — Pool resort test scene with individual beach chairs.
 *
 * Places 6 individual beach chairs (from beach_chair.glb) around a pool.
 * Uses world-space AABB centering after instantiation (handles Sketchfab
 * FBX scale matrices correctly) + SeatProber for sit height.
 */
import * as pc from 'playcanvas'
import type { AssetLoader } from '../assets/AssetLoader'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import { SeatProber } from '../characters/SeatProber'
import { POOL_CHAIRS, type PoolChairDef } from './SceneConfig'
import { InteractableItem } from './InteractableItem'

const BEACH_CHAIR_GLB = 'assets/garden/beach_chair.glb'

/** Target width for the beach chair in world units. */
const TARGET_CHAIR_WIDTH = 0.8

export interface PoolChairResult {
  def: PoolChairDef
  entity: pc.Entity
  probedSeatY: number | null
  seatWorldX: number
  seatWorldY: number
  seatWorldZ: number
  seatYaw: number
}

export class PoolScene {
  private loader: AssetLoader
  private materials: MaterialFactory | null
  private chairResults: PoolChairResult[] = []

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

    // Pool water
    const water = new pc.Entity('PoolWater')
    water.addComponent('render', { type: 'plane' })
    water.setLocalScale(6, 1, 6)
    water.setPosition(0, 0.05, 0)
    if (this.materials) {
      water.render!.meshInstances[0].material =
        this.materials.getColor('pool_water', 0.2, 0.5, 0.8, { emissive: [0.1, 0.25, 0.4] })
    }
    root.addChild(water)

    // Load beach chair asset once, instance per placement
    const chairAsset = await this.loader.load(BEACH_CHAIR_GLB)

    for (const chairDef of POOL_CHAIRS) {
      const result = await this.placeChair(root, chairAsset, chairDef)
      this.chairResults.push(result)

      const item = new InteractableItem(
        chairDef.id,
        new pc.Vec3(result.seatWorldX, 0, result.seatWorldZ),
        '[E] Sit in beach chair',
        `Relaxing... (seatY=${result.probedSeatY?.toFixed(3) ?? 'fallback'})`,
        'sit',
        {
          x: result.seatWorldX,
          z: result.seatWorldZ,
          yaw: chairDef.yaw,
          y: result.seatWorldY,
        },
        2.0,
      )
      this.items.push(item)
    }

    console.log('[PoolScene] SeatProber results:')
    for (const r of this.chairResults) {
      console.log(
        `  ${r.def.id}: probedSeatY=${r.probedSeatY?.toFixed(4) ?? 'null'}, ` +
        `worldY=${r.seatWorldY.toFixed(4)}, pos=(${r.seatWorldX.toFixed(2)}, ${r.seatWorldZ.toFixed(2)})`,
      )
    }
  }

  /**
   * Place a beach chair using world-space AABB centering.
   *
   * Sketchfab FBX exports have a 0.01 scale matrix baked into the node
   * hierarchy. `placeFurnitureCentered` uses local-space Mesh.aabb which
   * doesn't account for this, producing wrong offsets. Instead we:
   *   1. Instance the GLB and add to scene (so world transforms resolve)
   *   2. Measure the world-space AABB from MeshInstance.aabb
   *   3. Scale to fit TARGET_CHAIR_WIDTH
   *   4. Re-measure and offset so bottom-center is at placement coords
   */
  private async placeChair(
    parent: pc.Entity,
    asset: pc.Asset,
    def: PoolChairDef,
  ): Promise<PoolChairResult> {
    const model = this.loader.instance(asset)

    const wrapper = new pc.Entity(`BeachChair_${def.id}`)
    wrapper.addChild(model)
    wrapper.setLocalPosition(def.x, 0, def.z)
    if (def.yaw !== 0) wrapper.setLocalEulerAngles(0, def.yaw, 0)
    parent.addChild(wrapper)

    // World transforms now valid — measure AABB
    const meshInstances = this.collectMeshInstances(model)
    if (meshInstances.length === 0) {
      return { def, entity: wrapper, probedSeatY: null, seatWorldX: def.x, seatWorldY: 0.3, seatWorldZ: def.z, seatYaw: def.yaw }
    }

    // 1. Measure raw world AABB
    const rawAabb = this.worldAabb(meshInstances)
    const rawWidth = rawAabb.halfExtents.x * 2
    const scale = rawWidth > 0 ? TARGET_CHAIR_WIDTH / rawWidth : 1
    model.setLocalScale(scale, scale, scale)

    // 2. Force world transform update + re-measure
    wrapper.getWorldTransform()
    const scaledAabb = this.worldAabb(meshInstances)

    // 3. Offset so bottom-center is at (def.x, 0, def.z)
    const wrapperPos = wrapper.getPosition()
    const dx = scaledAabb.center.x - wrapperPos.x
    const dz = scaledAabb.center.z - wrapperPos.z
    const dy = (scaledAabb.center.y - scaledAabb.halfExtents.y) - wrapperPos.y
    const prev = model.getLocalPosition()
    model.setLocalPosition(prev.x - dx / scale, prev.y - dy / scale, prev.z - dz / scale)

    // 4. Probe seat Y from mesh geometry
    wrapper.getWorldTransform()
    const probedSeatY = SeatProber.probeSeatY(wrapper)
    const seatY = probedSeatY ?? 0.30

    return {
      def,
      entity: wrapper,
      probedSeatY,
      seatWorldX: def.x,
      seatWorldY: seatY,
      seatWorldZ: def.z,
      seatYaw: def.yaw,
    }
  }

  private collectMeshInstances(entity: pc.Entity): pc.MeshInstance[] {
    const out: pc.MeshInstance[] = []
    const renders = entity.findComponents('render') as pc.RenderComponent[]
    for (const rc of renders) out.push(...rc.meshInstances)
    return out
  }

  private worldAabb(instances: pc.MeshInstance[]): pc.BoundingBox {
    const aabb = new pc.BoundingBox()
    aabb.copy(instances[0].aabb)
    for (let i = 1; i < instances.length; i++) {
      aabb.add(instances[i].aabb)
    }
    return aabb
  }

  getAverageProbedSeatY(): number | null {
    const probed = this.chairResults
      .map(r => r.probedSeatY)
      .filter((y): y is number => y !== null)
    if (probed.length === 0) return null
    return probed.reduce((sum, y) => sum + y, 0) / probed.length
  }
}
