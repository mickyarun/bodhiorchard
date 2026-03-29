/**
 * HouseBuilder — Single member house with furnished interior.
 *
 * 4×4 tile footprint. Wall height is 1.29 units (measured from wall.glb).
 *
 * Uses placeFurnitureCentered() which auto-computes each model's AABB
 * and centers it at the given position. No manual origin offsets needed.
 *
 * Room layout (top-down, Z increases toward front):
 *
 *   z=0 [======= BACK WALL (solid) =======]
 *       | Lamp       Bed          Desk    |
 *   z=1 |                         Chair   |
 *       |                                 |
 *   z=2 |            Rug                  |
 *       |     Sofa          LoungeChair   |
 *   z=3 |                                 |
 *       | Plant       TV                  |
 *   z=4 [======= FRONT WALL (door) =======]
 *       x=0        door(x=1.5)       x=4
 *                    ○ ○ ○  ← stone path
 *   z=6
 */
import * as pc from 'playcanvas'
import { BuildingFactory } from './BuildingFactory'
import { BUILDING, PATH } from '../assets/AssetManifest'
import { setTreeData } from '../world/TreeNodeData'
import type { InteractionPoint } from '../characters/InteractionPoint'

const WALL_HEIGHT = 1.29

export interface HouseResult {
  entity: pc.Entity
  memberId: string
  memberName: string
  bedPosition: { x: number; y: number; z: number }
  seats: InteractionPoint[]
}

export class HouseBuilder {
  private factory: BuildingFactory

  constructor(factory: BuildingFactory) {
    this.factory = factory
  }

  async build(
    memberId: string,
    memberName: string,
    worldX: number,
    worldZ: number,
    index: number,
  ): Promise<HouseResult> {
    const root = new pc.Entity(`House_${memberName}`)
    root.setPosition(worldX, 0, worldZ)

    // Make house clickable by the picker system
    root.tags.add('pickable')
    setTreeData(root, { type: 'tree_house', memberId, memberName })

    const seats: InteractionPoint[] = []

    // Floor + Walls (4×4 tiles)
    await this.factory.createFloor(root, 4, 4)
    await this.factory.createWalls(root, 4, 4, [
      { side: 'front', index: 1, type: 'door' },
      { side: 'left', index: 1, type: 'window' },
      { side: 'left', index: 2, type: 'window' },
      { side: 'right', index: 1, type: 'window' },
      { side: 'right', index: 2, type: 'window' },
    ])

    // ─── Furniture (all positions are visual centers) ───

    // Bed — back-left area
    await this.factory.placeFurnitureCentered(root, BUILDING.bedSingle, 1.0, 0, 1.1)
    const bedPos = { x: worldX + 1.0, y: 0.38, z: worldZ + 1.1 }

    // Desk + laptop — back-right corner (laptop stacked on desk)
    const desk = await this.factory.placeFurnitureCentered(root, BUILDING.desk, 3.3, 0, 0.5)
    const deskHeight = BuildingFactory.getEntityHeight(desk)
    await this.factory.placeFurnitureCentered(root, BUILDING.laptop, 3.3, deskHeight, 0.5)

    // Chair at desk — face -Z toward desk (model front is +Z natively)
    const deskChair = await this.factory.placeSeat(root, BUILDING.chairDesk, 3.2, 1.3, 180, 'housing', index * 3, worldX, worldZ, 'chairDesk', 'typing')
    seats.push(deskChair.seat)

    // TV cabinet + TV — near front wall, screen facing -Z (TV stacked on cabinet)
    const cabinet = await this.factory.placeFurnitureCentered(root, BUILDING.cabinetTelevision, 2.0, 0, 3.7, 180)
    const cabinetHeight = BuildingFactory.getEntityHeight(cabinet)
    await this.factory.placeFurnitureCentered(root, BUILDING.televisionModern, 2.0, cabinetHeight, 3.7, 180)

    // Sofa — center of room, facing TV (+Z toward front wall)
    const sofa = await this.factory.placeSeat(root, BUILDING.loungeSofa, 1.5, 2.5, 0, 'housing', index * 3 + 1, worldX, worldZ, 'loungeSofa')
    seats.push(sofa.seat)

    // Lounge chair — right side, facing TV (+Z toward front wall)
    const loungeChair = await this.factory.placeSeat(root, BUILDING.loungeChair, 3.2, 2.5, 0, 'housing', index * 3 + 2, worldX, worldZ, 'loungeChair')
    seats.push(loungeChair.seat)

    // Decorations
    await this.factory.placeFurnitureCentered(root, BUILDING.lampRoundFloor, 0.4, 0, 0.4)
    await this.factory.placeFurnitureCentered(root, BUILDING.rugRound, 2.0, 0.01, 2.0)
    await this.factory.placeFurnitureCentered(root, BUILDING.plantSmall1, 0.5, 0, 3.5)

    // Roof
    this.factory.createRoof(root, 4, 4, WALL_HEIGHT)

    // ─── Front door stone path (3 stones extending outward) ───
    // Door is at tile index 1 → center at x=1.5, front wall at z=4.
    // Stones fit in the 2-unit gap before the next row (HOUSE_SPACING_Z=6).
    const doorCenterX = 1.5
    const stonePositions = [4.4, 5.0, 5.6]
    for (let j = 0; j < stonePositions.length; j++) {
      const stone = await this.factory.placeFurniture(
        root, PATH.stone, doorCenterX, 0.01, stonePositions[j], j * 30,
      )
      stone.setLocalScale(1.5, 1.5, 1.5)
    }

    return { entity: root, memberId, memberName, bedPosition: bedPos, seats }
  }
}
