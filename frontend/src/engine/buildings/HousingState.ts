// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * HousingState — owns everything SceneManager needs to know about the
 * housing village after `HousingVillage.build()` completes.
 *
 * Prior to extraction, `SceneManager` held half a dozen `_housing*` fields
 * and wired each one into physics/fence code manually. Collapsing them here
 * keeps housing concerns cohesive: adding a new housing-derived value
 * (e.g. "gate world normal", "lantern ring radius") is one-file.
 *
 * Lifecycle:
 *   1. `absorb(result)` — called once after HousingVillage finishes.
 *   2. `getOuterPerimeterRadius(worldRadius)` — called by SceneManager for
 *      both the outer rail fence and the Rapier perimeter collider (single
 *      derivation keeps the two in lockstep).
 *   3. `registerPhysicsFence(builder)` — wires the village rectangular
 *      fence into takeover physics using the cached local bounds + yaw +
 *      centre. No-op if no village was absorbed.
 *   4. `reset()` — wipes the cache. Called from SceneManager.teardown.
 */
import type { HousingVillage, HousingVillageResult } from './HousingVillage'
import type { FenceBounds } from '@shared/world/VillageLayout'
import type { TakeoverPhysicsBuilder } from '../takeover/TakeoverPhysicsBuilder'

/** Extra margin past the furthest structure to the outer rail. */
const OUTER_PERIMETER_MARGIN = 8

export class HousingState {
  village: HousingVillage | null = null
  /** World-space gate entrance — PathSystem routes here. */
  gatePosition: { x: number; z: number } | null = null
  /** Village fence corners in ZONE-LOCAL frame (axis-aligned, yaw-free). */
  fenceBoundsLocal: FenceBounds | null = null
  /** Village world centre (= housing zone x/z). */
  center: { x: number; z: number } | null = null
  /** Village yaw in radians — matches zone.yawDeg converted. */
  yawRad: number = 0
  /** Distance from origin to the furthest rotated village corner. */
  outerReach: number = 0
  /** Which wall carries the gate — used to resolve local gate coordinates. */
  gateSide: 'north' | 'south' | 'east' | 'west' = 'south'

  /** Populate state from a completed HousingVillage build. */
  absorb(village: HousingVillage, result: HousingVillageResult): void {
    this.village = village
    this.gatePosition = result.gatePosition
    this.fenceBoundsLocal = result.fenceBoundsLocal
    this.center = result.center
    this.yawRad = result.yawRad
    this.outerReach = result.outerReach
    this.gateSide = result.gateSide
  }

  /**
   * Outer perimeter radius used by BOTH the visual rail fence AND the
   * Rapier collider. Taking max(world-radius, village reach) means the
   * rail grows to enclose the housing village when member count pushes
   * its footprint past the static `housing.radius` in `shared/world/zones.ts`.
   */
  getOuterPerimeterRadius(staticWorldRadius: number): number {
    return Math.max(staticWorldRadius, this.outerReach) + OUTER_PERIMETER_MARGIN
  }

  /** Emit the village's rectangular fence into Rapier, yaw-aware. */
  registerPhysicsFence(builder: TakeoverPhysicsBuilder): void {
    if (!this.fenceBoundsLocal || !this.center) return
    const gateLocal = this.getGateLocal()
    if (!gateLocal) return
    builder.registerRectFence(this.fenceBoundsLocal, gateLocal, this.center, this.yawRad)
  }

  reset(): void {
    this.village = null
    this.gatePosition = null
    this.fenceBoundsLocal = null
    this.center = null
    this.yawRad = 0
    this.outerReach = 0
    this.gateSide = 'south'
  }

  /** Recover the gate position in zone-local coordinates from the cached bounds. */
  private getGateLocal(): { x: number; z: number } | null {
    const b = this.fenceBoundsLocal
    if (!b) return null
    const cx = (b.minX + b.maxX) / 2
    const cz = (b.minZ + b.maxZ) / 2
    switch (this.gateSide) {
      case 'north': return { x: cx, z: b.minZ }
      case 'south': return { x: cx, z: b.maxZ }
      case 'east':  return { x: b.maxX, z: cz }
      case 'west':  return { x: b.minX, z: cz }
    }
  }
}
