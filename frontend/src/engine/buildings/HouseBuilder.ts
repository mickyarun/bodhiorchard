/**
 * HouseBuilder — Single member house with furnished interior.
 *
 * Supports 3 tiers with different footprints and furniture:
 *
 *   Tier 1 (Hut)     — 3×3 tiles, basic furniture (bed, desk, lamp)
 *   Tier 2 (Cottage)  — 4×4 tiles, standard layout (current default)
 *   Tier 3 (Mansion)  — 5×5 tiles, expanded with luxury items
 *
 * Each tier uses BuildingFactory primitives (createFloor, createWalls,
 * placeFurnitureCentered, placeSeat). Furniture placement uses composite
 * operations (stacking, SeatProber) that don't reduce to config data,
 * so each tier has its own layout method.
 *
 * The public `build()` method accepts a tier parameter (default 2) so
 * existing callers work without modification.
 */
import * as pc from 'playcanvas'
import { BuildingFactory } from './BuildingFactory'
import { BUILDING, PATH } from '../assets/AssetManifest'
import { setTreeData } from '../world/TreeNodeData'
import { getHouseTier } from './HouseTierConfig'
import type { InteractionPoint } from '../characters/InteractionPoint'

/** Shared wall height constant — exported so takeover physics can match visual walls. */
export const WALL_HEIGHT = 1.29

/** Max seats per house across all tiers — used as seat index stride to prevent collisions in mixed-tier villages. */
const SEATS_PER_HOUSE = 4

export interface HouseResult {
  entity: pc.Entity
  memberId: string
  memberName: string
  characterModel: string | null
  tier: number
  bedPosition: { x: number; y: number; z: number }
  seats: InteractionPoint[]
  exitPosition: { x: number; z: number; yaw: number }
}

export class HouseBuilder {
  private factory: BuildingFactory

  constructor(factory: BuildingFactory) {
    this.factory = factory
  }

  async build(
    memberId: string,
    memberName: string,
    characterModel: string | null,
    worldX: number,
    worldZ: number,
    index: number,
    tier = 2,
  ): Promise<HouseResult> {
    const tierDef = getHouseTier(tier)
    const root = new pc.Entity(`House_${memberName}`)
    root.setPosition(worldX, 0, worldZ)

    root.tags.add('pickable')
    setTreeData(root, { type: 'tree_house', memberId, memberName })

    const seats: InteractionPoint[] = []

    // Floor + Walls (sized by tier)
    await this.factory.createFloor(root, tierDef.width, tierDef.depth)

    // Tier-specific interior layout
    let bedPos: { x: number; y: number; z: number }
    let exitPos: { x: number; z: number; yaw: number }

    switch (tier) {
      case 1:
        ({ bedPos, exitPos } = await this.layoutTier1(root, seats, worldX, worldZ, index, tierDef.width, tierDef.depth))
        break
      case 3:
        ({ bedPos, exitPos } = await this.layoutTier3(root, seats, worldX, worldZ, index, tierDef.width, tierDef.depth))
        break
      default:
        ({ bedPos, exitPos } = await this.layoutTier2(root, seats, worldX, worldZ, index, tierDef.width, tierDef.depth))
        break
    }

    // Roof
    this.factory.createRoof(root, tierDef.width, tierDef.depth, WALL_HEIGHT)

    return {
      entity: root,
      memberId,
      memberName,
      characterModel,
      tier,
      bedPosition: bedPos,
      seats,
      exitPosition: exitPos,
    }
  }

  // ─── Tier 1: Hut (3×3) ───────────────────────
  //
  //   z=0 [====== BACK WALL (solid) ======]
  //       | Lamp       Bed              |
  //   z=1 |                             |
  //       |            Desk    Chair    |
  //   z=2 |                             |
  //   z=3 [====== FRONT WALL (door) ====]
  //       x=0       door(x=1)       x=3

  private async layoutTier1(
    root: pc.Entity,
    seats: InteractionPoint[],
    worldX: number,
    worldZ: number,
    index: number,
    width: number,
    depth: number,
  ) {
    await this.factory.createWalls(root, width, depth, [
      { side: 'front', index: 1, type: 'door' },
    ])

    // Bed — back-left
    await this.factory.placeFurnitureCentered(root, BUILDING.bedSingle, 1.5, 0, 0.7)
    const bedPos = { x: worldX + 1.5, y: 0.38, z: worldZ + 0.7 }

    // Desk + chair — front-right area
    await this.factory.placeFurnitureCentered(root, BUILDING.desk, 2.2, 0, 1.8)
    const deskChair = await this.factory.placeSeat(root, BUILDING.chairDesk, 2.2, 2.3, 180, 'housing', index * SEATS_PER_HOUSE, worldX, worldZ, 'chairDesk', 'typing')
    seats.push(deskChair.seat)

    // Lamp — back-left corner
    await this.factory.placeFurnitureCentered(root, BUILDING.lampRoundFloor, 0.4, 0, 0.4)

    // Exit position — door at x=1, front wall at z=3
    const doorCenterX = 1.0
    const exitPos = {
      x: worldX + doorCenterX,
      z: worldZ + depth + 1.0,
      yaw: 0,
    }

    return { bedPos, exitPos }
  }

  // ─── Tier 2: Cottage (4×4) — current default layout ──────
  //
  //   z=0 [======= BACK WALL (solid) =======]
  //       | Lamp       Bed          Desk    |
  //   z=1 |                         Chair   |
  //       |                                 |
  //   z=2 |            Rug                  |
  //       |     Sofa          LoungeChair   |
  //   z=3 |                                 |
  //       | Plant       TV                  |
  //   z=4 [======= FRONT WALL (door) =======]
  //       x=0        door(x=1.5)       x=4

  private async layoutTier2(
    root: pc.Entity,
    seats: InteractionPoint[],
    worldX: number,
    worldZ: number,
    index: number,
    width: number,
    depth: number,
  ) {
    await this.factory.createWalls(root, width, depth, [
      { side: 'front', index: 1, type: 'door' },
      { side: 'left', index: 1, type: 'window' },
      { side: 'left', index: 2, type: 'window' },
      { side: 'right', index: 1, type: 'window' },
      { side: 'right', index: 2, type: 'window' },
    ])

    // Bed — back-left area
    await this.factory.placeFurnitureCentered(root, BUILDING.bedSingle, 1.0, 0, 1.1)
    const bedPos = { x: worldX + 1.0, y: 0.38, z: worldZ + 1.1 }

    // Desk + laptop — back-right corner
    const desk = await this.factory.placeFurnitureCentered(root, BUILDING.desk, 3.3, 0, 0.5)
    const deskHeight = BuildingFactory.getEntityHeight(desk)
    await this.factory.placeFurnitureCentered(root, BUILDING.laptop, 3.3, deskHeight, 0.5)

    // Chair at desk
    const deskChair = await this.factory.placeSeat(root, BUILDING.chairDesk, 3.2, 1.3, 180, 'housing', index * SEATS_PER_HOUSE, worldX, worldZ, 'chairDesk', 'typing')
    seats.push(deskChair.seat)

    // TV cabinet + TV
    const cabinet = await this.factory.placeFurnitureCentered(root, BUILDING.cabinetTelevision, 2.0, 0, 3.7, 180)
    const cabinetHeight = BuildingFactory.getEntityHeight(cabinet)
    await this.factory.placeFurnitureCentered(root, BUILDING.televisionModern, 2.0, cabinetHeight, 3.7, 180)

    // Sofa
    const sofa = await this.factory.placeSeat(root, BUILDING.loungeSofa, 1.5, 2.5, 0, 'housing', index * SEATS_PER_HOUSE + 1, worldX, worldZ, 'loungeSofa')
    seats.push(sofa.seat)

    // Lounge chair
    const loungeChair = await this.factory.placeSeat(root, BUILDING.loungeChair, 3.2, 2.5, 0, 'housing', index * SEATS_PER_HOUSE + 2, worldX, worldZ, 'loungeChair')
    seats.push(loungeChair.seat)

    // Decorations
    await this.factory.placeFurnitureCentered(root, BUILDING.lampRoundFloor, 0.4, 0, 0.4)
    await this.factory.placeFurnitureCentered(root, BUILDING.rugRound, 2.0, 0.01, 2.0)
    await this.factory.placeFurnitureCentered(root, BUILDING.plantSmall1, 0.5, 0, 3.5)

    // Front door stone path
    const doorCenterX = 1.5
    const stonePositions = [4.4, 5.0, 5.6]
    for (let j = 0; j < stonePositions.length; j++) {
      const stone = await this.factory.placeFurniture(
        root, PATH.stone, doorCenterX, 0.01, stonePositions[j], j * 30,
      )
      stone.setLocalScale(1.5, 1.5, 1.5)
    }

    // Exit position
    const exitPos = {
      x: worldX + doorCenterX,
      z: worldZ + 5.6,
      yaw: 0,
    }

    return { bedPos, exitPos }
  }

  // ─── Tier 3: Mansion (5×5) ────────────────────
  //
  //   z=0 [========== BACK WALL (solid) ==========]
  //       | Lamp  BedDouble       Desk    Books   |
  //   z=1 |       SideTable       Chair           |
  //       |                                       |
  //   z=2 |              RugRect                  |
  //       |     Sofa                LoungeChair   |
  //   z=3 |                                       |
  //       |  Plant  PottedPlant    TV    LampTbl  |
  //   z=4 |                                       |
  //   z=5 [========== FRONT WALL (door) ==========]
  //       x=0         door(x=2)              x=5

  private async layoutTier3(
    root: pc.Entity,
    seats: InteractionPoint[],
    worldX: number,
    worldZ: number,
    index: number,
    width: number,
    depth: number,
  ) {
    await this.factory.createWalls(root, width, depth, [
      { side: 'front', index: 2, type: 'door' },
      { side: 'left', index: 1, type: 'window' },
      { side: 'left', index: 2, type: 'window' },
      { side: 'left', index: 3, type: 'window' },
      { side: 'right', index: 1, type: 'window' },
      { side: 'right', index: 2, type: 'window' },
      { side: 'right', index: 3, type: 'window' },
    ])

    // Double bed — back-left area
    await this.factory.placeFurnitureCentered(root, BUILDING.bedDouble, 1.5, 0, 0.8)
    const bedPos = { x: worldX + 1.5, y: 0.38, z: worldZ + 0.8 }

    // Side table next to bed
    await this.factory.placeFurnitureCentered(root, BUILDING.sideTable, 0.5, 0, 0.8)

    // Desk + laptop — back-right area
    const desk = await this.factory.placeFurnitureCentered(root, BUILDING.desk, 3.5, 0, 0.5)
    const deskHeight = BuildingFactory.getEntityHeight(desk)
    await this.factory.placeFurnitureCentered(root, BUILDING.laptop, 3.5, deskHeight, 0.5)

    // Chair at desk
    const deskChair = await this.factory.placeSeat(root, BUILDING.chairDesk, 3.4, 1.3, 180, 'housing', index * SEATS_PER_HOUSE, worldX, worldZ, 'chairDesk', 'typing')
    seats.push(deskChair.seat)

    // Books on far-right back wall
    await this.factory.placeFurnitureCentered(root, BUILDING.books, 4.5, 0, 0.4)

    // TV cabinet + TV — near front wall
    const cabinet = await this.factory.placeFurnitureCentered(root, BUILDING.cabinetTelevision, 3.0, 0, 4.2, 180)
    const cabinetHeight = BuildingFactory.getEntityHeight(cabinet)
    await this.factory.placeFurnitureCentered(root, BUILDING.televisionModern, 3.0, cabinetHeight, 4.2, 180)

    // Sofa — center-left, facing TV
    const sofa = await this.factory.placeSeat(root, BUILDING.loungeSofa, 1.5, 3.0, 0, 'housing', index * SEATS_PER_HOUSE + 1, worldX, worldZ, 'loungeSofa')
    seats.push(sofa.seat)

    // Lounge chair — center-right, facing TV
    const loungeChair = await this.factory.placeSeat(root, BUILDING.loungeChair, 4.0, 3.0, 0, 'housing', index * SEATS_PER_HOUSE + 2, worldX, worldZ, 'loungeChair')
    seats.push(loungeChair.seat)

    // Decorations
    await this.factory.placeFurnitureCentered(root, BUILDING.lampRoundFloor, 0.4, 0, 0.4)
    await this.factory.placeFurnitureCentered(root, BUILDING.rugRectangle, 2.5, 0.01, 2.5)
    await this.factory.placeFurnitureCentered(root, BUILDING.plantSmall1, 0.5, 0, 4.2)
    await this.factory.placeFurnitureCentered(root, BUILDING.pottedPlant, 1.5, 0, 4.2)
    await this.factory.placeFurnitureCentered(root, BUILDING.lampRoundTable, 4.5, 0, 4.2)

    // Front door stone path (longer for mansion)
    const doorCenterX = 2.0
    const stonePositions = [5.4, 6.0, 6.6, 7.2]
    for (let j = 0; j < stonePositions.length; j++) {
      const stone = await this.factory.placeFurniture(
        root, PATH.stone, doorCenterX, 0.01, stonePositions[j], j * 25,
      )
      stone.setLocalScale(1.5, 1.5, 1.5)
    }

    // Exit position
    const exitPos = {
      x: worldX + doorCenterX,
      z: worldZ + 7.2,
      yaw: 0,
    }

    return { bedPos, exitPos }
  }
}
