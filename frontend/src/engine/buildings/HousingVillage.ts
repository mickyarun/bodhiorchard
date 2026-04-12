/**
 * HousingVillage — Grid of member houses.
 *
 * Creates N houses (one per member) in a grid layout within the
 * housing zone. Supports variable house tiers (different footprints).
 * Provides member→house mapping for NPC behaviors.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import type { EngineMember } from '../types'
import { HouseBuilder, type HouseResult } from './HouseBuilder'
import { BuildingFactory } from './BuildingFactory'
import type { AssetLoader } from '../assets/AssetLoader'
import { MAX_TIER_FOOTPRINT } from './HouseTierConfig'
import type { InteractionPoint } from '../characters/InteractionPoint'
import type { WorldLayout } from '../world/WorldLayout'
import type { ExclusionZone } from '../utils/MathUtils'

// Spacing accommodates the largest tier (5×5 mansion) + path + gap
const HOUSE_SPACING_X = 8
const HOUSE_SPACING_Z = 8
const HOUSES_PER_ROW = 4

export interface HousingVillageResult {
  entity: pc.Entity
  exclusionZone: ExclusionZone
  seats: InteractionPoint[]
  memberHouseMap: Map<string, HouseResult>
}

export class HousingVillage {
  private houseBuilder: HouseBuilder

  constructor(loader: AssetLoader) {
    this.houseBuilder = new HouseBuilder(new BuildingFactory(loader))
  }

  async build(
    app: Application,
    members: EngineMember[],
    layout: WorldLayout,
  ): Promise<HousingVillageResult> {
    const zone = layout.getZone('housing')
    const root = new pc.Entity('HousingVillage')
    const allSeats: InteractionPoint[] = []
    const memberHouseMap = new Map<string, HouseResult>()

    if (!zone || members.length === 0) {
      app.root.addChild(root)
      return {
        entity: root,
        exclusionZone: { x: 0, z: 0, radius: 0 },
        seats: allSeats,
        memberHouseMap,
      }
    }

    // Grid layout centered on the housing zone
    const cols = Math.min(HOUSES_PER_ROW, members.length)
    const rows = Math.ceil(members.length / cols)
    const totalWidth = (cols - 1) * HOUSE_SPACING_X
    const totalDepth = (rows - 1) * HOUSE_SPACING_Z

    for (let i = 0; i < members.length; i++) {
      const member = members[i]
      const col = i % cols
      const row = Math.floor(i / cols)

      const houseX = zone.x + col * HOUSE_SPACING_X - totalWidth / 2
      const houseZ = zone.z + row * HOUSE_SPACING_Z - totalDepth / 2

      const tier = member.house_level ?? 2

      const result = await this.houseBuilder.build(
        member.user_id, member.name, member.character_model,
        houseX, houseZ, i, tier,
      )

      // Rotate house 90° so front door faces +X instead of +Z.
      // World-space positions (seats, bed, exit) need manual transform:
      // 90° Y rotation maps local offset (dx, dz) → (dz, -dx).
      result.entity.setLocalEulerAngles(0, 90, 0)

      for (const seat of result.seats) {
        const dx = seat.x - houseX
        const dz = seat.z - houseZ
        seat.x = houseX + dz
        seat.z = houseZ - dx

        const adx = seat.approachX - houseX
        const adz = seat.approachZ - houseZ
        seat.approachX = houseX + adz
        seat.approachZ = houseZ - adx

        seat.yaw += 90
      }
      const bdx = result.bedPosition.x - houseX
      const bdz = result.bedPosition.z - houseZ
      result.bedPosition.x = houseX + bdz
      result.bedPosition.z = houseZ - bdx

      const edx = result.exitPosition.x - houseX
      const edz = result.exitPosition.z - houseZ
      result.exitPosition.x = houseX + edz
      result.exitPosition.z = houseZ - edx
      result.exitPosition.yaw += 90

      root.addChild(result.entity)
      allSeats.push(...result.seats)
      memberHouseMap.set(member.user_id, result)
    }

    app.root.addChild(root)

    return {
      entity: root,
      // Pad exclusion zone by max tier footprint + scatter buffer
      exclusionZone: { x: zone.x, z: zone.z, radius: zone.radius + MAX_TIER_FOOTPRINT + 2 },
      seats: allSeats,
      memberHouseMap,
    }
  }

  /**
   * Rebuild a single member's house at a new tier.
   * Destroys the old entity and builds a fresh one in place.
   * Returns the updated HouseResult for the caller to re-register
   * physics colliders and update the memberHouseMap.
   */
  async rebuildHouse(
    _app: Application,
    villageRoot: pc.Entity,
    oldResult: HouseResult,
    member: EngineMember,
    index: number,
    zoneX: number,
    zoneZ: number,
    cols: number,
    totalWidth: number,
    totalDepth: number,
  ): Promise<HouseResult> {
    // Destroy old house entity
    oldResult.entity.destroy()

    const col = index % cols
    const row = Math.floor(index / cols)
    const houseX = zoneX + col * HOUSE_SPACING_X - totalWidth / 2
    const houseZ = zoneZ + row * HOUSE_SPACING_Z - totalDepth / 2

    const tier = member.house_level ?? 2

    const result = await this.houseBuilder.build(
      member.user_id, member.name, member.character_model,
      houseX, houseZ, index, tier,
    )

    result.entity.setLocalEulerAngles(0, 90, 0)

    // Apply the same 90° rotation transforms as in build()
    for (const seat of result.seats) {
      const dx = seat.x - houseX
      const dz = seat.z - houseZ
      seat.x = houseX + dz
      seat.z = houseZ - dx

      const adx = seat.approachX - houseX
      const adz = seat.approachZ - houseZ
      seat.approachX = houseX + adz
      seat.approachZ = houseZ - adx

      seat.yaw += 90
    }
    const bdx = result.bedPosition.x - houseX
    const bdz = result.bedPosition.z - houseZ
    result.bedPosition.x = houseX + bdz
    result.bedPosition.z = houseZ - bdx

    const edx = result.exitPosition.x - houseX
    const edz = result.exitPosition.z - houseZ
    result.exitPosition.x = houseX + edz
    result.exitPosition.z = houseZ - edx
    result.exitPosition.yaw += 90

    villageRoot.addChild(result.entity)
    return result
  }
}
