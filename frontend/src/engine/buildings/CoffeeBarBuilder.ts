/**
 * CoffeeBarBuilder — Coffee bar with enclosed shelter + outdoor seating.
 *
 * Layout (top-down, Z increases toward front):
 *
 *   z=0 [========= BACK WALL (solid) =========]
 *       | Cabinet   Bar+Coffee    Stove       |
 *   z=1 |          (stacked)                  |
 *       |                                     |
 *   z=2 [========= FRONT (3 doors) ===========]
 *       x=0                                x=3
 *
 *   Outdoor seating (z=3 to z=7):
 *     Left row:  tableCoffee + 2 chairs (×2)
 *     Right row: tableCoffee + 2 chairs (×2)
 *     Central campfire between rows
 *
 * Placement rules:
 * - All furniture uses placeFurnitureCentered (consistent AABB centering)
 * - Stacking: base placed first, getEntityHeight for top Y, stacked item
 *   placed at that Y — same pattern as HouseBuilder (desk+laptop, cabinet+TV)
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import { BuildingFactory } from './BuildingFactory'
import { BUILDING, CAMPFIRE } from '../assets/AssetManifest'
import type { InteractionPoint } from '../characters/InteractionPoint'
import type { ExclusionZone } from '../utils/MathUtils'

const WALL_HEIGHT = 1.29
const HUT_WIDTH = 3
const HUT_DEPTH = 2

export interface CoffeeBarResult {
  entity: pc.Entity
  exclusionZone: ExclusionZone
  seats: InteractionPoint[]
}

export class CoffeeBarBuilder {
  private factory: BuildingFactory

  constructor(factory: BuildingFactory) {
    this.factory = factory
  }

  async build(app: Application, x: number, z: number): Promise<CoffeeBarResult> {
    const root = new pc.Entity('CoffeeBar')
    root.setPosition(x, 0, z)

    const seats: InteractionPoint[] = []

    // ─── Shelter hut (3×2 tiles, open front) ───
    await this.factory.createFloor(root, 3, 2)
    await this.factory.createWalls(root, 3, 2, [
      { side: 'front', index: 0, type: 'door' },
      { side: 'front', index: 1, type: 'door' },
      { side: 'front', index: 2, type: 'door' },
      { side: 'left', index: 0, type: 'window' },
      { side: 'right', index: 0, type: 'window' },
    ])
    this.factory.createRoof(root, 3, 2, WALL_HEIGHT)

    // ─── Interior: back wall equipment ───
    // All items use placeFurnitureCentered for consistent AABB centering.
    // Stacking follows HouseBuilder pattern (desk+laptop, cabinet+TV).

    // Left: kitchen cabinet against back wall
    await this.factory.placeFurnitureCentered(
      root, BUILDING.kitchenCabinet, 0.5, 0, 0.5,
    )

    // Center: bar counter with coffee machine stacked on top
    const bar = await this.factory.placeFurnitureCentered(
      root, BUILDING.kitchenBar, 1.5, 0, 0.7,
    )
    const barHeight = BuildingFactory.getEntityHeight(bar)
    await this.factory.placeFurnitureCentered(
      root, BUILDING.kitchenCoffeeMachine, 1.5, barHeight, 0.7,
    )

    // Right: kitchen stove against back wall
    await this.factory.placeFurnitureCentered(
      root, BUILDING.kitchenStove, 2.5, 0, 0.5,
    )

    // ─── Outdoor seating (z=3 to z=7) ───
    let seatIndex = 0

    // Left row — two coffee tables with chairs facing each other
    for (let i = 0; i < 2; i++) {
      const tz = 3.5 + i * 2.0
      await this.factory.placeFurnitureCentered(root, BUILDING.tableCoffee, -1.0, 0, tz)
      const left = await this.factory.placeSeat(root, BUILDING.chairCushion, -1.8, tz, 90, 'coffee_bar', seatIndex++, x, z, 'chairCushion', 'interact-right')
      const right = await this.factory.placeSeat(root, BUILDING.chairCushion, -0.2, tz, -90, 'coffee_bar', seatIndex++, x, z, 'chairCushion', 'interact-right')
      seats.push(left.seat, right.seat)
    }

    // Right row — two coffee tables with chairs facing each other
    for (let i = 0; i < 2; i++) {
      const tz = 3.5 + i * 2.0
      await this.factory.placeFurnitureCentered(root, BUILDING.tableCoffee, 2.5, 0, tz)
      const left = await this.factory.placeSeat(root, BUILDING.chairCushion, 1.7, tz, 90, 'coffee_bar', seatIndex++, x, z, 'chairCushion', 'interact-right')
      const right = await this.factory.placeSeat(root, BUILDING.chairCushion, 3.3, tz, -90, 'coffee_bar', seatIndex++, x, z, 'chairCushion', 'interact-right')
      seats.push(left.seat, right.seat)
    }

    // Central campfire between the two seating rows
    await this.factory.placeFurniture(root, CAMPFIRE.stones, 0.8, 0, 4.5)
    await this.factory.placeFurniture(root, CAMPFIRE.logs, 0.8, 0.1, 4.5)

    // Add to scene at the END — consistent with other builders.
    app.root.addChild(root)

    // ─── String lights (local coords, part of building entity) ───
    // Poles at hut front corners, strings frame the outdoor seating area.
    const stringH = WALL_HEIGHT + 1.2
    this.factory.createStringLights(root, [
      // Left side of outdoor area
      { start: { x: -2, y: stringH, z: HUT_DEPTH }, end: { x: -2, y: stringH, z: 6.5 }, bulbCount: 3 },
      // Right side of outdoor area
      { start: { x: HUT_WIDTH + 1, y: stringH, z: HUT_DEPTH }, end: { x: HUT_WIDTH + 1, y: stringH, z: 6.5 }, bulbCount: 3 },
      // Cross-string at hut front
      { start: { x: -2, y: stringH, z: HUT_DEPTH }, end: { x: HUT_WIDTH + 1, y: stringH, z: HUT_DEPTH }, bulbCount: 4 },
    ])

    return {
      entity: root,
      exclusionZone: { x, z, radius: 8 },
      seats,
    }
  }
}
