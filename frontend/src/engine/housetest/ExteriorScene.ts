/**
 * ExteriorScene — Multi-house village with Rapier physics.
 *
 * Builds N houses from EXTERIOR_HOUSES config, each as a 4×4-tile Kenney
 * house shell with roof, stone path, and name label. Registers all wall
 * collision and door sensors with PhysicsWorld.
 *
 * Visual entities are created under the provided root entity.
 * Physics bodies are created in the shared PhysicsWorld instance.
 */
import * as pc from 'playcanvas'
import { BuildingFactory } from '../buildings/BuildingFactory'
import { PATH } from '../assets/AssetManifest'
import {
  WALL_COLLISION,
  EXTERIOR_HOUSES,
  HOUSE_DOOR_LOCAL,
  type ExteriorHouseDef,
} from './SceneConfig'
import type { PhysicsWorld } from '../physics'

const WALL_HEIGHT  = 1.29
const GROUND_SIZE  = 30
const GROUND_COLOR = { r: 0.45, g: 0.65, b: 0.35 }

export class ExteriorScene {
  private factory: BuildingFactory

  constructor(factory: BuildingFactory) {
    this.factory = factory
  }

  /**
   * Build the multi-house village and register physics.
   * @param root - Parent entity for all visual elements
   * @param physics - PhysicsWorld to register wall bodies and door sensors
   */
  async build(root: pc.Entity, physics: PhysicsWorld): Promise<void> {
    this.buildGround(root, physics)

    for (const house of EXTERIOR_HOUSES) {
      await this.buildHouse(root, house, physics)
    }
  }

  private buildGround(root: pc.Entity, physics: PhysicsWorld): void {
    const ground = new pc.Entity('Ground')
    ground.addComponent('render', { type: 'plane' })
    const mat = this.factory.materialFactory?.getColor(
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

    // Physics ground plane
    physics.addGround(-0.05, GROUND_SIZE)
  }

  private async buildHouse(
    root: pc.Entity,
    house: ExteriorHouseDef,
    physics: PhysicsWorld,
  ): Promise<void> {
    // Parent entity offset to house world position
    const houseRoot = new pc.Entity(`House_${house.id}`)
    houseRoot.setPosition(house.x, 0, house.z)
    root.addChild(houseRoot)

    // Visual: floor, walls, roof
    await this.factory.createFloor(houseRoot, 4, 4)
    await this.factory.createWalls(houseRoot, 4, 4, [
      { side: 'front', index: 1, type: 'door' },
      { side: 'left',  index: 1, type: 'window' },
      { side: 'left',  index: 2, type: 'window' },
      { side: 'right', index: 1, type: 'window' },
      { side: 'right', index: 2, type: 'window' },
    ])
    this.factory.createRoof(houseRoot, 4, 4, WALL_HEIGHT)

    // Visual: stone path leading to door
    const stoneZPositions = [4.4, 5.0, 5.6]
    for (let i = 0; i < stoneZPositions.length; i++) {
      const stone = await this.factory.placeFurniture(
        houseRoot, PATH.stone, 1.5, 0.01, stoneZPositions[i], i * 30,
      )
      stone.setLocalScale(1.5, 1.5, 1.5)
    }

    // Visual: name label above house
    const label = new pc.Entity(`Label_${house.id}`)
    label.addComponent('render', { type: 'plane' })
    label.setLocalPosition(2, WALL_HEIGHT + 0.5, 2)
    label.setLocalScale(2, 1, 0.4)
    label.setLocalEulerAngles(90, 0, 0)
    houseRoot.addChild(label)

    // Physics: register wall collision bodies (world-space)
    this.registerWallPhysics(house.x, house.z, physics)

    // Physics: door sensor (world-space)
    physics.addSensor(
      `door_${house.id}`,
      house.x + HOUSE_DOOR_LOCAL.x,   // world X center of door
      0.5,                              // Y center (mid-height)
      house.z + HOUSE_DOOR_LOCAL.z,   // world Z (just outside door)
      0.5,                              // halfW (1-unit wide door gap)
      0.5,                              // halfH
      0.3,                              // halfD (thin trigger zone)
    )
  }

  /**
   * Register wall physics bodies for one house at world position (hx, hz).
   * Creates 5 static cuboid colliders matching WALL_COLLISION boxes
   * (4 walls + front wall split for door gap).
   */
  private registerWallPhysics(hx: number, hz: number, physics: PhysicsWorld): void {
    for (const box of WALL_COLLISION) {
      const cx = hx + (box.minX + box.maxX) / 2
      const cy = WALL_HEIGHT / 2
      const cz = hz + (box.minZ + box.maxZ) / 2
      const halfW = (box.maxX - box.minX) / 2
      const halfH = WALL_HEIGHT / 2
      const halfD = (box.maxZ - box.minZ) / 2
      physics.addStaticBox(cx, cy, cz, halfW, halfH, halfD)
    }
  }
}
