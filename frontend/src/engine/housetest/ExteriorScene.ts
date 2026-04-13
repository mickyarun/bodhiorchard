/**
 * ExteriorScene — Multi-house village with tiered building models.
 *
 * Tier 0 (Standard)  — Original Kenney procedural house (walls + flat roof)
 * Tier 1 (Hut)       — KayKit home_small.glb
 * Tier 2 (Cottage)   — KayKit home_medium.glb
 * Tier 3 (Mansion)   — KayKit home_large.glb (tavern/manor)
 *
 * Standard is the default every member starts with. KayKit tiers are
 * visual upgrades unlocked with SP.
 */
import * as pc from 'playcanvas'
import { BuildingFactory } from '../buildings/BuildingFactory'
import { PATH } from '../assets/AssetManifest'
import type { AssetLoader } from '../assets/AssetLoader'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import {
  WALL_COLLISION,
  EXTERIOR_HOUSES,
  HOUSE_DOOR_LOCAL,
  type ExteriorHouseDef,
} from './SceneConfig'
import type { PhysicsWorld } from '../physics'
import { createNameLabel } from '../characters/NameLabel'

const WALL_HEIGHT  = 1.29
const GROUND_SIZE  = 30
const GROUND_COLOR = { r: 0.45, g: 0.65, b: 0.35 }

// ─── KayKit tier model config ─────────────────────

interface TierModel {
  glb: string
  scale: number
  footprint: { w: number; d: number }
}

const KAYKIT_MODELS: Record<1 | 2 | 3, TierModel> = {
  1: {
    glb: 'assets/buildings/kaykit/home_small.glb',
    scale: 1.8,
    footprint: { w: 1.8, d: 1.8 },
  },
  2: {
    glb: 'assets/buildings/kaykit/home_medium.glb',
    scale: 1.8,
    footprint: { w: 2.2, d: 2.2 },
  },
  3: {
    glb: 'assets/buildings/kaykit/home_barracks.glb',
    scale: 1.5,
    footprint: { w: 3.0, d: 3.0 },
  },
}

export class ExteriorScene {
  private loader: AssetLoader
  private materials: MaterialFactory | null
  private factory: BuildingFactory

  constructor(loader: AssetLoader, materials?: MaterialFactory) {
    this.loader = loader
    this.materials = materials ?? null
    this.factory = new BuildingFactory(loader, materials)
  }

  async build(root: pc.Entity, physics: PhysicsWorld): Promise<void> {
    this.buildGround(root, physics)

    for (const house of EXTERIOR_HOUSES) {
      if (house.tier === 0) {
        await this.buildStandardHouse(root, house, physics)
      } else {
        await this.buildKayKitHouse(root, house, physics)
      }
    }
  }

  // ─── Ground ─────────────────────────────────────

  private buildGround(root: pc.Entity, physics: PhysicsWorld): void {
    const ground = new pc.Entity('Ground')
    ground.addComponent('render', { type: 'plane' })
    const mat = this.materials?.getColor(
      'housetest_ground', GROUND_COLOR.r, GROUND_COLOR.g, GROUND_COLOR.b,
    ) ?? (() => {
      const m = new pc.StandardMaterial()
      m.diffuse.set(GROUND_COLOR.r, GROUND_COLOR.g, GROUND_COLOR.b)
      m.update()
      return m
    })()
    ground.render!.meshInstances[0].material = mat
    ground.setLocalScale(GROUND_SIZE, 1, GROUND_SIZE)
    ground.setLocalPosition(GROUND_SIZE / 2 - 5, -0.005, GROUND_SIZE / 2 - 3)
    root.addChild(ground)
    physics.addGround(-0.05, GROUND_SIZE)
  }

  // ─── Tier 0: Standard Kenney house (procedural) ─

  private async buildStandardHouse(
    root: pc.Entity,
    house: ExteriorHouseDef,
    physics: PhysicsWorld,
  ): Promise<void> {
    const houseRoot = new pc.Entity(`House_${house.id}`)
    houseRoot.setPosition(house.x, 0, house.z)
    root.addChild(houseRoot)

    // Floor + walls + flat roof (original code)
    await this.factory.createFloor(houseRoot, 4, 4)
    await this.factory.createWalls(houseRoot, 4, 4, [
      { side: 'front', index: 1, type: 'door' },
      { side: 'left',  index: 1, type: 'window' },
      { side: 'left',  index: 2, type: 'window' },
      { side: 'right', index: 1, type: 'window' },
      { side: 'right', index: 2, type: 'window' },
    ])
    this.factory.createRoof(houseRoot, 4, 4, WALL_HEIGHT)

    // Stone path
    for (let i = 0; i < 3; i++) {
      const stone = await this.factory.placeFurniture(
        houseRoot, PATH.stone, 1.5, 0.01, 4.4 + i * 0.6, i * 30,
      )
      stone.setLocalScale(1.5, 1.5, 1.5)
    }

    // Name label
    const label = createNameLabel(house.label, this.loader.app.graphicsDevice, WALL_HEIGHT + 0.4)
    label.setLocalPosition(2, 0, 2)
    houseRoot.addChild(label)

    // Physics
    for (const box of WALL_COLLISION) {
      physics.addStaticBox(
        house.x + (box.minX + box.maxX) / 2,
        WALL_HEIGHT / 2,
        house.z + (box.minZ + box.maxZ) / 2,
        (box.maxX - box.minX) / 2,
        WALL_HEIGHT / 2,
        (box.maxZ - box.minZ) / 2,
      )
    }
    physics.addDoor(
      house.id,
      house.x + HOUSE_DOOR_LOCAL.x,
      WALL_HEIGHT / 2,
      house.z + 4.0,
      0.45, WALL_HEIGHT / 2, 0.05,
    )
  }

  // ─── Tier 1-3: KayKit whole-model buildings ─────

  private async buildKayKitHouse(
    root: pc.Entity,
    house: ExteriorHouseDef,
    physics: PhysicsWorld,
  ): Promise<void> {
    const tier = house.tier as 1 | 2 | 3
    const model = KAYKIT_MODELS[tier]

    const asset = await this.loader.load(model.glb)
    const building = this.loader.instance(asset)
    building.name = `House_${house.id}`
    building.setPosition(house.x, 0, house.z)
    building.setLocalScale(model.scale, model.scale, model.scale)
    root.addChild(building)

    // Stone path leading to front
    const stoneCount = tier + 1
    for (let i = 0; i < stoneCount; i++) {
      const stone = await this.factory.placeFurniture(
        root, PATH.stone,
        house.x, 0.01, house.z + (model.footprint.d * model.scale) / 2 + 0.4 + i * 0.6,
        i * 30,
      )
      stone.setLocalScale(1.5, 1.5, 1.5)
    }

    // Name label above building
    const labelY = model.footprint.w * model.scale + 0.3
    const label = createNameLabel(house.label, this.loader.app.graphicsDevice, labelY)
    label.setLocalPosition(house.x, 0, house.z)
    root.addChild(label)

    // Physics: simple box collider matching footprint
    const { w, d } = model.footprint
    const s = model.scale
    physics.addStaticBox(
      house.x, WALL_HEIGHT / 2, house.z,
      (w * s) / 2, WALL_HEIGHT / 2, (d * s) / 2,
    )
    physics.addDoor(
      house.id,
      house.x,
      WALL_HEIGHT / 2,
      house.z + (d * s) / 2,
      0.45, WALL_HEIGHT / 2, 0.05,
    )
  }
}
