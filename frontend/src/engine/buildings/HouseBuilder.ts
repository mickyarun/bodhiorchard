/**
 * HouseBuilder — Single member house with furnished interior.
 *
 * Supports 3 tiers with different footprints and furniture:
 *
 *   Tier 1 (Hut)     — 3×3 tiles, basic furniture (bed, desk, lamp)
 *   Tier 2 (Cottage)  — 4×4 tiles, standard layout (KayKit exterior)
 *   Tier 3 (Mansion)  — 5×5 tiles, expanded with luxury items
 *
 * Each tier uses BuildingFactory primitives (createFloor, createWalls,
 * placeFurnitureCentered, placeSeat). Furniture placement uses composite
 * operations (stacking, SeatProber) that don't reduce to config data,
 * so each tier has its own layout method.
 *
 * The public `build()` method accepts a tier parameter (default 1) so
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

// ─── House Nameboard ─────────────────────────────

const BOARD_TEX_W = 320
const BOARD_TEX_H = 80
const BOARD_WORLD_W = 1.6
const BOARD_WORLD_H = BOARD_WORLD_W * (BOARD_TEX_H / BOARD_TEX_W)

/**
 * Create a wooden-plank-style nameboard for a house.
 * Uses canvas pre-flip so text reads correctly under billboard rotation.
 * Tagged 'billboard' for Application's per-frame camera-facing loop.
 */
function createHouseNameboard(
  name: string,
  device: pc.GraphicsDevice,
  height: number,
): pc.Entity {
  const canvas = document.createElement('canvas')
  canvas.width = BOARD_TEX_W
  canvas.height = BOARD_TEX_H
  const ctx = canvas.getContext('2d')!
  ctx.clearRect(0, 0, BOARD_TEX_W, BOARD_TEX_H)

  // Pre-flip horizontally — billboard lookAt views the plane from behind,
  // so mirroring the canvas content makes text read correctly in 3D.
  ctx.translate(BOARD_TEX_W, 0)
  ctx.scale(-1, 1)

  // Wooden plank background
  const pad = 6
  const r = 8
  ctx.fillStyle = '#3E2723' // dark wood brown
  ctx.beginPath()
  ctx.moveTo(pad + r, pad)
  ctx.arcTo(BOARD_TEX_W - pad, pad, BOARD_TEX_W - pad, BOARD_TEX_H - pad, r)
  ctx.arcTo(BOARD_TEX_W - pad, BOARD_TEX_H - pad, pad, BOARD_TEX_H - pad, r)
  ctx.arcTo(pad, BOARD_TEX_H - pad, pad, pad, r)
  ctx.arcTo(pad, pad, BOARD_TEX_W - pad, pad, r)
  ctx.closePath()
  ctx.fill()

  // Subtle wood grain line
  ctx.strokeStyle = 'rgba(255,255,255,0.08)'
  ctx.lineWidth = 1
  ctx.beginPath()
  ctx.moveTo(pad + 10, BOARD_TEX_H / 2)
  ctx.lineTo(BOARD_TEX_W - pad - 10, BOARD_TEX_H / 2)
  ctx.stroke()

  // Light border
  ctx.strokeStyle = '#5D4037'
  ctx.lineWidth = 2
  ctx.beginPath()
  ctx.moveTo(pad + r, pad)
  ctx.arcTo(BOARD_TEX_W - pad, pad, BOARD_TEX_W - pad, BOARD_TEX_H - pad, r)
  ctx.arcTo(BOARD_TEX_W - pad, BOARD_TEX_H - pad, pad, BOARD_TEX_H - pad, r)
  ctx.arcTo(pad, BOARD_TEX_H - pad, pad, pad, r)
  ctx.arcTo(pad, pad, BOARD_TEX_W - pad, pad, r)
  ctx.closePath()
  ctx.stroke()

  // White text with slight shadow
  ctx.shadowColor = 'rgba(0,0,0,0.5)'
  ctx.shadowBlur = 3
  ctx.shadowOffsetY = 1
  ctx.fillStyle = '#FFFDE7' // warm white
  ctx.font = 'bold 28px "Segoe UI", Arial, sans-serif'
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillText(name, BOARD_TEX_W / 2, BOARD_TEX_H / 2, BOARD_TEX_W - pad * 4)

  const texture = new pc.Texture(device, {
    width: BOARD_TEX_W, height: BOARD_TEX_H,
    format: pc.PIXELFORMAT_RGBA8,
    minFilter: pc.FILTER_LINEAR, magFilter: pc.FILTER_LINEAR,
  })
  const pixels = texture.lock()
  pixels.set(ctx.getImageData(0, 0, BOARD_TEX_W, BOARD_TEX_H).data)
  texture.unlock()

  const mat = new pc.StandardMaterial()
  mat.diffuseMap = texture
  mat.emissiveMap = texture
  mat.emissive = new pc.Color(1, 1, 1)
  mat.opacityMap = texture
  mat.opacityMapChannel = 'a'
  mat.blendType = pc.BLEND_NORMAL
  mat.depthWrite = false
  mat.cull = pc.CULLFACE_NONE
  mat.update()

  const entity = new pc.Entity('HouseNameboard')
  entity.addComponent('render', { type: 'plane' })
  entity.render!.meshInstances[0].material = mat
  entity.setLocalPosition(0, height, 0)
  entity.setLocalScale(BOARD_WORLD_W, 1, BOARD_WORLD_H)
  entity.setLocalEulerAngles(90, 0, 0)
  entity.tags.add('billboard')

  return entity
}

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
  /** Pivot center + yaw, set by HousingVillage. Used by TakeoverPhysicsBuilder. */
  pivotX?: number
  pivotZ?: number
  pivotYaw?: number
  /**
   * Measured world-space half-extents of the KayKit exterior GLB after scaling.
   * Set only for tier 2/3 where the visual comes from a loaded model whose
   * real footprint (including roof overhangs) differs from the interior floor
   * plan. Physics uses this to size the wall collider to match the visual.
   */
  exteriorHalfW?: number
  exteriorHalfD?: number
}

export class HouseBuilder {
  private factory: BuildingFactory
  private device: pc.GraphicsDevice

  constructor(factory: BuildingFactory, device: pc.GraphicsDevice) {
    this.factory = factory
    this.device = device
  }

  async build(
    memberId: string,
    memberName: string,
    characterModel: string | null,
    worldX: number,
    worldZ: number,
    index: number,
    tier = 1,
  ): Promise<HouseResult> {
    const tierDef = getHouseTier(tier)
    const root = new pc.Entity(`House_${memberName}`)
    root.setPosition(worldX, 0, worldZ)

    root.tags.add('pickable')
    setTreeData(root, { type: 'tree_house', memberId, memberName })

    const seats: InteractionPoint[] = []

    let bedPos: { x: number; y: number; z: number }
    let exitPos: { x: number; z: number; yaw: number }
    let measuredHalfW: number | undefined
    let measuredHalfD: number | undefined

    if (tierDef.exteriorGlb) {
      // KayKit whole-building model (tier 2/3).
      //
      // Scale the GLB so its visible footprint matches the interior tile size
      // (tierDef.width × depth, TILE_SIZE=1m). Without this, tier 3's mansion
      // renders visibly larger than the interior floor plan — characters
      // standing next to the collider edge appear to be "inside" the mansion
      // walls in takeover mode.
      //
      // placeFurnitureCentered wraps the GLB in an entity that offsets the
      // model to center-bottom, so the visual center ends up exactly at
      // (targetHalfW, 0, targetHalfD) — the interior center.
      const targetHalfW = tierDef.width / 2
      const targetHalfD = tierDef.depth / 2

      const building = await this.factory.placeFurnitureCentered(
        root, tierDef.exteriorGlb, targetHalfW, 0, targetHalfD,
      )

      // Measure raw (unscaled) mesh AABB — always valid, independent of the
      // wrapper's local scale. Compute a uniform scale so the most-constrained
      // axis exactly hits the interior size; the other axis can only be
      // smaller or equal, never exceeding the interior footprint.
      const raw = BuildingFactory.getEntityFootprint(building)
      let s = tierDef.exteriorScale ?? 1.0
      if (raw.halfW > 0 && raw.halfD > 0) {
        s = Math.min(targetHalfW / raw.halfW, targetHalfD / raw.halfD)
      }
      building.setLocalScale(s, s, s)

      measuredHalfW = raw.halfW * s
      measuredHalfD = raw.halfD * s

      // Nameboard above the building — sits at interior center, height scaled
      // with the building so it floats just above the roof.
      const labelY = targetHalfW * 2 * s + 0.3
      const board = createHouseNameboard(memberName, this.device, labelY)
      board.setLocalPosition(targetHalfW, 0, targetHalfD)
      root.addChild(board)

      // Default bed/exit positions for KayKit tiers (interior handles actual placement).
      // Exit is centered on the door (doorIndex + 0.5), 1 unit past the front
      // wall (depth + 1), facing away (yaw 0) — same convention as Kenney tiers.
      const doorCenterX = tierDef.doorIndex + 0.5
      bedPos = { x: worldX + 1, y: 0, z: worldZ + 0.5 }
      exitPos = { x: worldX + doorCenterX, z: worldZ + tierDef.depth + 1.0, yaw: 0 }
    } else {
      // Kenney procedural house (tier 1)
      await this.factory.createFloor(root, tierDef.width, tierDef.depth)

      switch (tier) {
        case 1:
          ({ bedPos, exitPos } = await this.layoutTier1(root, seats, worldX, worldZ, index, tierDef.width, tierDef.depth, tierDef.doorIndex))
          break
        case 3:
          ({ bedPos, exitPos } = await this.layoutTier3(root, seats, worldX, worldZ, index, tierDef.width, tierDef.depth, tierDef.doorIndex))
          break
        default:
          ({ bedPos, exitPos } = await this.layoutTier2(root, seats, worldX, worldZ, index, tierDef.width, tierDef.depth, tierDef.doorIndex))
          break
      }

      // Roof (Kenney only)
      this.factory.createRoof(root, tierDef.width, tierDef.depth, WALL_HEIGHT)

      // Nameboard above roof
      const board = createHouseNameboard(memberName, this.device, WALL_HEIGHT + 0.4)
      board.setLocalPosition(tierDef.width / 2, 0, tierDef.depth / 2)
      root.addChild(board)
    }

    return {
      entity: root,
      memberId,
      memberName,
      characterModel,
      tier,
      bedPosition: bedPos,
      seats,
      exitPosition: exitPos,
      exteriorHalfW: measuredHalfW,
      exteriorHalfD: measuredHalfD,
    }
  }

  // ─── Tier 1: Hut (3×3) ───────────────────────
  //
  //   z=0 [====== BACK WALL (solid) ======]
  //       | Lamp  Bed                     |
  //   z=1 |                  Desk  Chair  |
  //       |                               |
  //   z=2 [====== FRONT WALL (door) ======]
  //       x=0     door(x=1)            x=3

  private async layoutTier1(
    root: pc.Entity,
    seats: InteractionPoint[],
    worldX: number,
    worldZ: number,
    index: number,
    width: number,
    depth: number,
    doorIndex: number,
  ) {
    await this.factory.createWalls(root, width, depth, [
      { side: 'front', index: doorIndex, type: 'door' },
    ])

    // Bed — back-left
    await this.factory.placeFurnitureCentered(root, BUILDING.bedSingle, 1.0, 0, 0.7)
    const bedPos = { x: worldX + 1.0, y: 0.38, z: worldZ + 0.7 }

    // Desk + chair — back-right
    await this.factory.placeFurnitureCentered(root, BUILDING.desk, 2.2, 0, 0.5)
    const deskChair = await this.factory.placeSeat(root, BUILDING.chairDesk, 2.2, 1.3, 180, 'housing', index * SEATS_PER_HOUSE, worldX, worldZ, 'chairDesk', 'typing')
    seats.push(deskChair.seat)

    // Lamp — back-left corner
    await this.factory.placeFurnitureCentered(root, BUILDING.lampRoundFloor, 0.4, 0, 0.4)

    // Exit position — door spans corner-local x=[doorIndex, doorIndex+1].
    // Front wall at z=depth. Exit is 1 unit in front of the wall, centered on the door.
    const doorCenterX = doorIndex + 0.5
    const exitPos = {
      x: worldX + doorCenterX,
      z: worldZ + depth + 1.0,
      yaw: 0,
    }

    return { bedPos, exitPos }
  }

  // ─── Tier 2: Cottage (4×4) ──────
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
    doorIndex: number,
  ) {
    await this.factory.createWalls(root, width, depth, [
      { side: 'front', index: doorIndex, type: 'door' },
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

    // Front door stone path — door spans x=[doorIndex, doorIndex+1], center at +0.5.
    const doorCenterX = doorIndex + 0.5
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
    doorIndex: number,
  ) {
    await this.factory.createWalls(root, width, depth, [
      { side: 'front', index: doorIndex, type: 'door' },
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

    // Front door stone path (longer for mansion). Door spans x=[doorIndex, doorIndex+1].
    const doorCenterX = doorIndex + 0.5
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
