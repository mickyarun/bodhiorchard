// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * HousingVillage — Double-row street village for the production dashboard.
 *
 * Uses `computeVillageLayout` from `@shared/world/VillageLayout` for house
 * placement. The layout is emitted in zone-LOCAL coordinates (yaw-free,
 * centred on 0,0); this class sets the village root entity's world
 * position + yaw from the housing zone, so every child (houses, roads,
 * fence, driveways) inherits the visual rotation automatically.
 *
 * HouseResult coordinates stay LOCAL forever: seats / bedPosition /
 * exitPosition are never mutated into world space. Consumers read them
 * via `toWorld(localPoint, house.pivot)` from `@shared/world/geom`.
 */
import * as pc from 'playcanvas'
import type { Application } from '../core/Application'
import type { EngineMember } from '../types'
import { HouseBuilder, type HouseResult } from './HouseBuilder'
import { BuildingFactory } from './BuildingFactory'
import type { AssetLoader } from '../assets/AssetLoader'
import type { MaterialFactory } from '../rendering/MaterialFactory'
import { getHouseTier, MAX_TIER_FOOTPRINT } from './HouseTierConfig'
import type { InteractionPoint } from '../characters/InteractionPoint'
import type { WorldLayout } from '../world/WorldLayout'
import type { ExclusionZone } from '../utils/MathUtils'
import { SandRoadBuilder } from '../world/SandRoadBuilder'
import { RectangularFence } from '../world/RectangularFence'
import { LabelRenderer } from '../rendering/LabelRenderer'
import {
  computeVillageLayout,
  type FenceBounds,
  type VillageLayoutResult,
} from '@shared/world/VillageLayout'
import type { Zone } from '@shared/world/zones'
import { rotatePointAroundPivot, toWorld } from '@shared/world/geom'

// ─── Types ───────────────────────────────────────

export interface HousingVillageResult {
  entity: pc.Entity
  exclusionZone: ExclusionZone
  seats: InteractionPoint[]
  memberHouseMap: Map<string, HouseResult>
  fenceRadius: number
  /** Axis-aligned rectangle in zone-LOCAL space (yaw-free). */
  fenceBoundsLocal: FenceBounds
  /** World-space centre of the village (= housing zone x/z). */
  center: { x: number; z: number }
  /** Village yaw in radians — physics + derived world computations read this. */
  yawRad: number
  /** Distance from world origin to the furthest rotated village fence corner. */
  outerReach: number
  /** Gate entrance in world space — PathSystem routes here. */
  gatePosition: { x: number; z: number }
  /** Gate side relative to the zone-local rectangle. Passed to RectangularFence. */
  gateSide: 'north' | 'south' | 'east' | 'west'
}

// ─── Village Builder ─────────────────────────────

export class HousingVillage {
  private houseBuilder: HouseBuilder
  private roads: SandRoadBuilder

  /** Stored context for live tier rebuilds. */
  private buildContext: {
    app: Application
    villageRoot: pc.Entity
    zone: Zone
    members: EngineMember[]
    layout: VillageLayoutResult
    memberHouseMap: Map<string, HouseResult>
    currentUserId: string | null
  } | null = null

  constructor(loader: AssetLoader) {
    const factory = new BuildingFactory(loader)
    this.houseBuilder = new HouseBuilder(factory)
    this.roads = new SandRoadBuilder(loader)
  }

  async build(
    app: Application,
    members: EngineMember[],
    worldLayout: WorldLayout,
    currentUserId: string | null,
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
        fenceRadius: 10, fenceBoundsLocal: emptyBounds,
        center: { x: zone?.x ?? 0, z: zone?.z ?? 0 },
        yawRad: 0,
        outerReach: 0,
        gatePosition: { x: 0, z: 0 },
        gateSide: 'south',
      }
    }

    const villageMems = members.map(m => ({
      user_id: m.user_id, name: m.name, house_level: m.house_level,
    }))
    const layout = computeVillageLayout(villageMems, zone)

    // Root carries the village's world position AND yaw; all children are
    // placed in LOCAL coordinates and inherit the transform visually.
    root.setPosition(zone.x, 0, zone.z)
    root.setLocalEulerAngles(0, zone.yawDeg ?? 0, 0)

    // Roads + driveways — placements are local, root's yaw rotates them visually.
    await this.roads.init()
    this.roads.buildRoads(root, layout.streets, layout.placements, { driveways: true })

    // Fence — bounds are zone-local, gateSide picked in the same frame.
    const gateSide = this.computeGateSide(zone)
    if (materials) {
      new RectangularFence(materials).build(root, { bounds: layout.fenceBounds, gateSide })
    }

    // ─── Houses: build LOCAL, wrap with pivot, compose yaw ─────────────
    for (const placement of layout.placements) {
      const member = members[placement.layoutIndex]
      const tier = member.house_level ?? 1

      const result = await this.houseBuilder.build(
        app, member.user_id, member.name, member.character_model,
        placement.x, placement.z, placement.layoutIndex, tier,
        member.user_id === currentUserId,
      )

      this.wrapWithPivot(root, result, placement, zone, tier)

      // WorldLayout.getSeats() returns seats in world coords across every
      // zone (coffee bar, cafeteria, pool, pavilion emit world directly).
      // HouseResult seats stay LOCAL — push world-space clones here so the
      // two readers don't race on a single mutated object.
      const pivot = result.pivot
      if (pivot) {
        for (const s of result.seats) {
          const w = toWorld(s, pivot)
          allSeats.push({
            ...s,
            x: w.x, z: w.z,
            approachX: toWorld({ x: s.approachX, z: s.approachZ }, pivot).x,
            approachZ: toWorld({ x: s.approachX, z: s.approachZ }, pivot).z,
            yaw: s.yaw + pivot.yawDeg,
          })
        }
      }
      memberHouseMap.set(member.user_id, result)
    }

    app.root.addChild(root)

    const gateLocal = this.computeGateLocal(layout.fenceBounds, gateSide)
    const gatePosition = this.localToWorld(gateLocal.x, gateLocal.z, zone, layout.yawRad)

    this.buildContext = { app, villageRoot: root, zone, members, layout, memberHouseMap, currentUserId }

    return {
      entity: root,
      exclusionZone: { x: zone.x, z: zone.z, radius: layout.fenceRadius + MAX_TIER_FOOTPRINT },
      seats: allSeats, memberHouseMap,
      fenceRadius: layout.fenceRadius,
      fenceBoundsLocal: layout.fenceBounds,
      center: { x: zone.x, z: zone.z },
      yawRad: layout.yawRad,
      outerReach: layout.outerReach,
      gatePosition,
      gateSide,
    }
  }

  // ─── Pivot Wrapper ─────────────────────────────

  /**
   * Wrap a HouseBuilder result with a pivot entity at the placement's
   * LOCAL coordinates under the village root. The village root already
   * carries position + yaw, so the pivot itself only composes the house's
   * own yaw (0 for north side, 180 for south). HouseResult's
   * seats/bedPosition/exitPosition stay LOCAL (corner-origin); `pivot`
   * is written with WORLD position and composed yaw for downstream
   * consumers that need world coordinates.
   */
  private wrapWithPivot(
    parent: pc.Entity,
    result: HouseResult,
    placement: { x: number; z: number; yawDeg: number },
    zone: Zone,
    tier: number,
  ): void {
    const tierDef = getHouseTier(tier)

    // Corner → centre offset. HouseBuilder lays the house out in a
    // (tierDef.width × tierDef.depth) tile footprint from (0,0); halving
    // those gives the pivot-to-corner delta consistently across tiers.
    const ox = -tierDef.width / 2
    const oz = -tierDef.depth / 2

    // Pivot lives at the placement's LOCAL coordinates under the rotated
    // village root. House-yaw (0 or 180) is purely local; the village
    // yaw is already on the root.
    const pivot = new pc.Entity(`HousePivot_${result.memberId}`)
    pivot.setLocalPosition(placement.x, 0, placement.z)
    pivot.setLocalEulerAngles(0, placement.yawDeg, 0)
    parent.addChild(pivot)

    pivot.addChild(result.entity)
    result.entity.setLocalPosition(ox, 0, oz)
    result.entity.setLocalEulerAngles(0, 0, 0)

    // Replace entity reference so destroy() tears down the pivot subtree.
    result.entity = pivot

    // Composed WORLD transform: rotate placement around zone centre, then
    // translate to world; compose house yaw with village yaw. Seats /
    // bedPosition / exitPosition remain LOCAL (never mutated).
    const villageYawRad = ((zone.yawDeg ?? 0) * Math.PI) / 180
    const worldXZ = rotatePointAroundPivot(
      placement.x + zone.x, placement.z + zone.z, villageYawRad, zone.x, zone.z,
    )
    result.pivot = {
      x: worldXZ.x,
      z: worldXZ.z,
      yawDeg: placement.yawDeg + (zone.yawDeg ?? 0),
    }
  }

  // ─── Gate Helpers ──────────────────────────────

  /**
   * Pick which wall of the zone-local rectangle houses the gate. Works
   * at any rotation: we transform "direction from zone to origin" into
   * the zone-local frame, then pick the wall whose outward normal
   * best matches it.
   */
  private computeGateSide(zone: Zone): 'north' | 'south' | 'east' | 'west' {
    const yawRad = ((zone.yawDeg ?? 0) * Math.PI) / 180
    const dx = -zone.x, dz = -zone.z               // world → origin
    const cos = Math.cos(yawRad), sin = Math.sin(yawRad)
    // Inverse of rotatePointAroundPivot's forward direction — rotate the
    // world-space direction vector into zone-local.
    const lx =  dx * cos - dz * sin
    const lz =  dx * sin + dz * cos
    return Math.abs(lx) > Math.abs(lz)
      ? (lx > 0 ? 'east'  : 'west')
      : (lz > 0 ? 'south' : 'north')
  }

  private computeGateLocal(
    bounds: FenceBounds,
    side: 'north' | 'south' | 'east' | 'west',
  ): { x: number; z: number } {
    const cx = (bounds.minX + bounds.maxX) / 2
    const cz = (bounds.minZ + bounds.maxZ) / 2
    switch (side) {
      case 'north': return { x: cx, z: bounds.minZ }
      case 'south': return { x: cx, z: bounds.maxZ }
      case 'east':  return { x: bounds.maxX, z: cz }
      case 'west':  return { x: bounds.minX, z: cz }
    }
  }

  private localToWorld(
    lx: number, lz: number,
    zone: Zone, yawRad: number,
  ): { x: number; z: number } {
    return rotatePointAroundPivot(lx + zone.x, lz + zone.z, yawRad, zone.x, zone.z)
  }

  // ─── Live Rebuild ──────────────────────────────

  async rebuildByMemberId(memberId: string, newTier: number): Promise<void> {
    if (!this.buildContext) return
    const { app, villageRoot, zone, members, layout, memberHouseMap, currentUserId } = this.buildContext

    const oldResult = memberHouseMap.get(memberId)
    if (!oldResult) return

    const placement = layout.placements.find(p => p.memberId === memberId)
    if (!placement) return

    const member = members[placement.layoutIndex]
    member.house_level = newTier

    // Unregister the old nameplate billboard before destroying the pivot tree.
    // PlayCanvas's recursive destroy frees the entity, but Application.billboards
    // would otherwise hold a stale reference.
    if (oldResult.nameLabel) LabelRenderer.cleanup(app, oldResult.nameLabel)
    oldResult.entity.destroy()

    const result = await this.houseBuilder.build(
      app, member.user_id, member.name, member.character_model,
      placement.x, placement.z, placement.layoutIndex, newTier,
      member.user_id === currentUserId,
    )

    this.wrapWithPivot(villageRoot, result, placement, zone, newTier)
    memberHouseMap.set(memberId, result)
  }
}
