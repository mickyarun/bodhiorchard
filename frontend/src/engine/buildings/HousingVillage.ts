// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * HousingVillage — Double-row street village for the production dashboard.
 *
 * Uses VillageLayout.computeVillageLayout() for house placement,
 * then builds houses with the pivot wrapper pattern (same as housetest)
 * so rotation happens around the house center, not the corner.
 *
 * Also builds sand-strip roads, driveways, and a square fence.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import type { EngineMember } from '../types'
import { HouseBuilder, type HouseResult } from './HouseBuilder'
import { BuildingFactory } from './BuildingFactory'
import type { AssetLoader } from '../assets/AssetLoader'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import { getHouseTier } from './HouseTierConfig'
import { MAX_TIER_FOOTPRINT } from './HouseTierConfig'
import type { InteractionPoint } from '../characters/InteractionPoint'
import type { WorldLayout } from '../world/WorldLayout'
import type { ExclusionZone } from '../utils/MathUtils'
import { SandRoadBuilder } from '../world/SandRoadBuilder'
import { RectangularFence } from '../world/RectangularFence'
import {
  computeVillageLayout,
  type FenceBounds,
  type VillageLayoutResult,
} from './VillageLayout'

// ─── Types ───────────────────────────────────────

export interface HousingVillageResult {
  entity: pc.Entity
  exclusionZone: ExclusionZone
  seats: InteractionPoint[]
  memberHouseMap: Map<string, HouseResult>
  fenceRadius: number
  fenceBounds: FenceBounds
  /** Distance from world origin to the furthest village fence corner. */
  outerReach: number
  /** World-space gate entrance point — PathSystem routes to here. */
  gatePosition: { x: number; z: number }
}

// ─── Village Builder ─────────────────────────────

export class HousingVillage {
  private houseBuilder: HouseBuilder
  private roads: SandRoadBuilder

  /** Stored context for live tier rebuilds. */
  private buildContext: {
    villageRoot: pc.Entity
    members: EngineMember[]
    layout: VillageLayoutResult
    memberHouseMap: Map<string, HouseResult>
  } | null = null

  constructor(loader: AssetLoader) {
    const factory = new BuildingFactory(loader)
    this.houseBuilder = new HouseBuilder(factory, loader.app.graphicsDevice)
    this.roads = new SandRoadBuilder(loader)
  }

  async build(
    app: Application,
    members: EngineMember[],
    worldLayout: WorldLayout,
    materials?: MaterialFactory,
  ): Promise<HousingVillageResult> {
    const zone = worldLayout.getZone('housing')
    const root = new pc.Entity('HousingVillage')
    const allSeats: InteractionPoint[] = []
    const memberHouseMap = new Map<string, HouseResult>()
    const emptyBounds: FenceBounds = { minX: 0, maxX: 0, minZ: 0, maxZ: 0 }

    if (!zone || members.length === 0) {
      app.root.addChild(root)
      return {
        entity: root,
        exclusionZone: { x: 0, z: 0, radius: 0 },
        seats: allSeats, memberHouseMap,
        fenceRadius: 10, fenceBounds: emptyBounds,
        outerReach: 0,
        gatePosition: { x: 0, z: 0 },
      }
    }

    const villageMems = members.map(m => ({
      user_id: m.user_id, name: m.name, house_level: m.house_level,
    }))
    const layout = computeVillageLayout(villageMems, zone.x, zone.z)

    // Roads + driveways (centeredOrigin — pivot pattern centers houses)
    await this.roads.init()
    this.roads.buildRoads(root, layout.streets, layout.placements, { driveways: true })

    // Fence
    if (materials) {
      const gateSide = this.computeGateSide(zone.x, zone.z)
      new RectangularFence(materials).build(root, { bounds: layout.fenceBounds, gateSide })
    }

    // ─── Houses (pivot wrapper pattern) ─────────────────────────
    for (const placement of layout.placements) {
      const member = members[placement.layoutIndex]
      const tier = member.house_level ?? 1

      const result = await this.houseBuilder.build(
        member.user_id, member.name, member.character_model,
        placement.x, placement.z, placement.layoutIndex, tier,
      )

      this.wrapWithPivot(root, result, placement.x, placement.z, placement.yawDeg, tier)

      allSeats.push(...result.seats)
      memberHouseMap.set(member.user_id, result)
    }

    app.root.addChild(root)

    const gatePosition = this.computeGatePosition(layout.fenceBounds, zone.x, zone.z)
    this.buildContext = { villageRoot: root, members, layout, memberHouseMap }

    return {
      entity: root,
      exclusionZone: { x: zone.x, z: zone.z, radius: layout.fenceRadius + MAX_TIER_FOOTPRINT },
      seats: allSeats, memberHouseMap,
      fenceRadius: layout.fenceRadius,
      fenceBounds: layout.fenceBounds,
      outerReach: layout.outerReach,
      gatePosition,
    }
  }

  // ─── Pivot Wrapper ─────────────────────────────

  /**
   * Wrap a HouseBuilder result with a pivot entity so the house center
   * is at the placement position and rotation happens around center.
   *
   * HouseBuilder builds from corner (0,0 → w,d). The pivot offsets the
   * entity by (-w/2, -d/2) so the center aligns with the placement.
   */
  private wrapWithPivot(
    parent: pc.Entity,
    result: HouseResult,
    px: number, pz: number,
    yawDeg: number, tier: number,
  ): void {
    const tierDef = getHouseTier(tier)

    // Centering offset: from corner-origin to center-origin. The HouseBuilder
    // lays out the house (procedural walls or scaled KayKit GLB) within a
    // tierDef.width × tierDef.depth tile footprint, so halving those gives the
    // pivot-to-corner delta consistently across all tiers — no special case
    // for KayKit. This is the single source of truth for house centering.
    const ox = -tierDef.width / 2
    const oz = -tierDef.depth / 2

    // Create pivot at placement center with rotation
    const pivot = new pc.Entity(`HousePivot_${result.memberId}`)
    pivot.setPosition(px, 0, pz)
    pivot.setLocalEulerAngles(0, yawDeg, 0)
    parent.addChild(pivot)

    // Add house entity as child, offset to center
    pivot.addChild(result.entity)
    result.entity.setLocalPosition(ox, 0, oz)
    result.entity.setLocalEulerAngles(0, 0, 0)  // yaw is on pivot

    // Shift data positions by centering offset, then rotate around center
    this.shiftPositions(result, ox, oz)
    this.applyRotation(result, px, pz, yawDeg)

    // Replace entity reference with the pivot (for destroy/rebuild)
    result.entity = pivot

    // Store explicit pivot data for physics (avoids entity transform reference issues)
    result.pivotX = px
    result.pivotZ = pz
    result.pivotYaw = yawDeg
  }

  // ─── Position Transforms ───────────────────────

  /** Shift all data positions by (ox, oz) to account for centering offset. */
  private shiftPositions(result: HouseResult, ox: number, oz: number): void {
    for (const seat of result.seats) {
      seat.x += ox; seat.z += oz
      seat.approachX += ox; seat.approachZ += oz
    }
    result.bedPosition.x += ox
    result.bedPosition.z += oz
    result.exitPosition.x += ox
    result.exitPosition.z += oz
  }

  /** Rotate all data positions around (cx, cz) by yawDeg. */
  private applyRotation(result: HouseResult, cx: number, cz: number, yawDeg: number): void {
    const rad = yawDeg * Math.PI / 180
    const cos = Math.cos(rad)
    const sin = Math.sin(rad)

    for (const seat of result.seats) {
      const dx = seat.x - cx, dz = seat.z - cz
      seat.x = cx + dx * cos + dz * sin
      seat.z = cz - dx * sin + dz * cos
      const ax = seat.approachX - cx, az = seat.approachZ - cz
      seat.approachX = cx + ax * cos + az * sin
      seat.approachZ = cz - ax * sin + az * cos
      seat.yaw += yawDeg
    }

    const bdx = result.bedPosition.x - cx, bdz = result.bedPosition.z - cz
    result.bedPosition.x = cx + bdx * cos + bdz * sin
    result.bedPosition.z = cz - bdx * sin + bdz * cos

    const edx = result.exitPosition.x - cx, edz = result.exitPosition.z - cz
    result.exitPosition.x = cx + edx * cos + edz * sin
    result.exitPosition.z = cz - edx * sin + edz * cos
    result.exitPosition.yaw += yawDeg
  }

  // ─── Gate Helpers ──────────────────────────────

  private computeGateSide(zoneX: number, zoneZ: number): 'north' | 'south' | 'east' | 'west' {
    const ax = Math.abs(zoneX), az = Math.abs(zoneZ)
    if (ax > az) return zoneX > 0 ? 'west' : 'east'
    return zoneZ > 0 ? 'north' : 'south'
  }

  private computeGatePosition(bounds: FenceBounds, zoneX: number, zoneZ: number): { x: number; z: number } {
    const cx = (bounds.minX + bounds.maxX) / 2
    const cz = (bounds.minZ + bounds.maxZ) / 2
    switch (this.computeGateSide(zoneX, zoneZ)) {
      case 'north': return { x: cx, z: bounds.minZ }
      case 'south': return { x: cx, z: bounds.maxZ }
      case 'east':  return { x: bounds.maxX, z: cz }
      case 'west':  return { x: bounds.minX, z: cz }
    }
  }

  // ─── Live Rebuild ──────────────────────────────

  async rebuildByMemberId(memberId: string, newTier: number): Promise<void> {
    if (!this.buildContext) return
    const { villageRoot, members, layout, memberHouseMap } = this.buildContext

    const oldResult = memberHouseMap.get(memberId)
    if (!oldResult) return

    const placement = layout.placements.find(p => p.memberId === memberId)
    if (!placement) return

    const member = members[placement.layoutIndex]
    member.house_level = newTier

    // Destroy old pivot (which contains the house entity)
    oldResult.entity.destroy()

    const result = await this.houseBuilder.build(
      member.user_id, member.name, member.character_model,
      placement.x, placement.z, placement.layoutIndex, newTier,
    )

    this.wrapWithPivot(villageRoot, result, placement.x, placement.z, placement.yawDeg, newTier)
    memberHouseMap.set(memberId, result)
  }
}
