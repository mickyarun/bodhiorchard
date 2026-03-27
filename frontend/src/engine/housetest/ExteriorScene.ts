/**
 * ExteriorScene — Kenney house shell with surrounding ground.
 *
 * Builds the 4×4-tile Kenney house (walls + roof) using the same
 * BuildingFactory methods as the main dashboard. Returns AABB collision
 * boxes so PlayerController blocks at walls, leaving a gap at the door
 * opening (X: 1.0–2.0 on the front wall at Z=4).
 *
 * The house sits at the scene's local origin (0, 0, 0).
 * Player starts outside at Z=7, walks toward Z=4 to enter.
 */
import * as pc from 'playcanvas'
import { BuildingFactory } from '../buildings/BuildingFactory'
import { PATH } from '../assets/AssetManifest'
import { WALL_COLLISION } from './SceneConfig'
import type { CollisionBox } from './CollisionSystem'

const WALL_HEIGHT  = 1.29
const GROUND_SIZE  = 20
// Linear-space RGB — matches the garden's green ground palette
const GROUND_COLOR = { r: 0.45, g: 0.65, b: 0.35 }

/** Door tile is front-wall index=1 → center X=1.5, gap X=1.0–2.0. */
export const DOOR_ENTER_POS = new pc.Vec3(1.5, 0, 4.7)

export class ExteriorScene {
  private factory: BuildingFactory

  constructor(factory: BuildingFactory) {
    this.factory = factory
  }

  async build(root: pc.Entity): Promise<CollisionBox[]> {
    this.buildGround(root)
    await this.buildHouseShell(root)
    await this.buildStonePath(root)
    return this.buildCollisionBoxes()
  }

  private buildGround(root: pc.Entity): void {
    // Flat green ground plane under everything
    const ground = new pc.Entity('Ground')
    ground.addComponent('render', { type: 'plane' })
    // Use shared MaterialFactory when available (cached, properly-lit PBR material).
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
    // Plane pivot is at center — shift so house (0–4, 0–4) sits naturally on it
    ground.setLocalPosition(GROUND_SIZE / 2 - 2, -0.005, GROUND_SIZE / 2 - 2)
    root.addChild(ground)
  }

  private async buildHouseShell(root: pc.Entity): Promise<void> {
    await this.factory.createFloor(root, 4, 4)
    await this.factory.createWalls(root, 4, 4, [
      { side: 'front', index: 1, type: 'door' },
      { side: 'left',  index: 1, type: 'window' },
      { side: 'left',  index: 2, type: 'window' },
      { side: 'right', index: 1, type: 'window' },
      { side: 'right', index: 2, type: 'window' },
    ])
    this.factory.createRoof(root, 4, 4, WALL_HEIGHT)
  }

  private async buildStonePath(root: pc.Entity): Promise<void> {
    const stoneZPositions = [4.4, 5.0, 5.6]
    for (let i = 0; i < stoneZPositions.length; i++) {
      const stone = await this.factory.placeFurniture(
        root, PATH.stone, 1.5, 0.01, stoneZPositions[i], i * 30,
      )
      stone.setLocalScale(1.5, 1.5, 1.5)
    }
  }

  private buildCollisionBoxes(): CollisionBox[] {
    // Shared wall boxes defined in SceneConfig — single source of truth for both scenes.
    return WALL_COLLISION
  }
}
