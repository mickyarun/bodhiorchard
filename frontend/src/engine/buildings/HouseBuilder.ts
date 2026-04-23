// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

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
import { BUILDING } from '../assets/AssetManifest'
import { setTreeData } from '../world/TreeNodeData'
import { getHouseTier, BED_SURFACE_Y } from './HouseTierConfig'
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

/**
 * World-space pivot of a placed house. Carries the composed rotation
 * (house yaw + village yaw) so consumers can always map HouseResult's
 * LOCAL coordinates to world via `toWorld(localPoint, pivot)`.
 */
export interface HousePivot {
  x: number
  z: number
  yawDeg: number
}

export interface HouseResult {
  entity: pc.Entity
  memberId: string
  memberName: string
  characterModel: string | null
  tier: number
  /** Bed mattress surface position — LOCAL to the house tile (corner-origin). */
  bedPosition: { x: number; y: number; z: number }
  /** Interaction seats — LOCAL to the house tile. Consumers use `toWorld(seat, pivot)`. */
  seats: InteractionPoint[]
  /** Door exit spawn — LOCAL to the house tile. */
  exitPosition: { x: number; z: number; yaw: number }
  /**
   * World-space pivot + composed yaw. Written by `HousingVillage.wrapWithPivot`
   * after placement. The sole authoritative transform from house-local
   * coordinates to world space — consumers read `pivot` and apply
   * `toWorld` rather than reading `seats`/`bedPosition` as world directly.
   *
   * Undefined for a freshly-built (un-placed) HouseResult; set once wrapped.
   */
  pivot?: HousePivot
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

      // Nameboard above the building — measured from the actual GLB roof height.
      const labelY = BuildingFactory.getEntityHeight(building) * s + 0.3
      const board = createHouseNameboard(memberName, this.device, labelY)
      board.setLocalPosition(targetHalfW, 0, targetHalfD)
      root.addChild(board)

      // Bed/exit from tier config — same source of truth as Kenney and multiplayer.
      bedPos = { x: worldX + tierDef.bed.x, y: BED_SURFACE_Y, z: worldZ + tierDef.bed.z }
      const doorCenterX = tierDef.doorIndex + 0.5
      exitPos = { x: worldX + doorCenterX, z: worldZ + tierDef.depth + 1.0, yaw: 0 }
    } else {
      // Kenney procedural house (tier 1)
      await this.factory.createFloor(root, tierDef.width, tierDef.depth)

      // Only tier 1 uses Kenney procedural — tiers with exteriorGlb take the
      // KayKit branch above. If a future Kenney tier is added, restore a switch.
      ;({ bedPos, exitPos } = await this.layoutTier1(root, seats, worldX, worldZ, index, tierDef.width, tierDef.depth, tierDef.doorIndex))

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

    // Bed — position from tier config
    const tierDef1 = getHouseTier(1)
    await this.factory.placeFurnitureCentered(root, BUILDING.bedSingle, tierDef1.bed.x, 0, tierDef1.bed.z)
    const bedPos = { x: worldX + tierDef1.bed.x, y: BED_SURFACE_Y, z: worldZ + tierDef1.bed.z }

    // Desk + chair — position from tier config
    await this.factory.placeFurnitureCentered(root, BUILDING.desk, tierDef1.desk.x, 0, 0.5)
    const deskChair = await this.factory.placeSeat(root, BUILDING.chairDesk, tierDef1.desk.x, tierDef1.desk.z, tierDef1.desk.yaw, 'housing', index * SEATS_PER_HOUSE, worldX, worldZ, 'chairDesk', 'typing')
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

}
