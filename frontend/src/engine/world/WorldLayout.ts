// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * WorldLayout — Master layout: zone positions + exclusion zones + seat registry.
 *
 * Zone coordinates and tiers come from `@shared/world/zones` so the
 * multiplayer server and the client stay in sync automatically. To
 * move a zone, edit shared/world/zones.ts — NOT this file.
 */
import { ZONES as SHARED_ZONES, type Zone, type ZoneTier } from '@shared/world/zones'
import { getTreePositions as sharedGetTreePositions } from '@shared/world/treePositions'
import type { ExclusionZone } from '../utils/MathUtils'
import type { InteractionPoint } from '../characters/InteractionPoint'

/** Backward-compatible alias — use InteractionPoint in new code. */
export type SeatSlot = InteractionPoint

// ─── Zone Definitions (re-export from shared) ───────────────────────────

export type { ZoneTier }

/** Client-side alias of the shared Zone type. Kept as WorldZone for
 *  historical reasons — many builders import WorldZone directly. */
export type WorldZone = Zone

const ZONES: WorldZone[] = SHARED_ZONES

export class WorldLayout {
  private zones: WorldZone[]
  private exclusionZones: ExclusionZone[] = []
  private seats: InteractionPoint[] = []

  constructor() {
    this.zones = [...ZONES]
  }

  /** Get a named zone. */
  getZone(name: string): WorldZone | undefined {
    return this.zones.find(z => z.name === name)
  }

  /** Get all zones. */
  getAllZones(): readonly WorldZone[] {
    return this.zones
  }

  /** Get the world radius (outermost zone edge). */
  getWorldRadius(): number {
    let max = 0
    for (const z of this.zones) {
      const edge = Math.sqrt(z.x * z.x + z.z * z.z) + z.radius
      if (edge > max) max = edge
    }
    return max
  }

  // ─── Exclusion Zones ──────────────────────────

  /** Add exclusion zones (buildings, trees). */
  addExclusionZones(zones: ExclusionZone[]): void {
    this.exclusionZones.push(...zones)
  }

  /** Get all exclusion zones for scatter systems. */
  getExclusionZones(): readonly ExclusionZone[] {
    return this.exclusionZones
  }

  /** Clear all dynamic exclusion zones (for rebuild). */
  clearExclusionZones(): void {
    this.exclusionZones = []
  }

  // ─── Seat Registry ────────────────────────────

  /** Register interaction points from a building. */
  registerSeats(seats: InteractionPoint[]): void {
    this.seats.push(...seats)
  }

  /** Get all interaction points, optionally filtered by zone name. */
  getSeats(zone?: string): readonly InteractionPoint[] {
    if (!zone) return this.seats
    return this.seats.filter(s => s.zone === zone)
  }

  /** Find the first unoccupied point in a zone. */
  findAvailable(zone: string): InteractionPoint | null {
    return this.seats.find(s => s.zone === zone && !s.occupied) ?? null
  }

  /** Mark a point as occupied by a member. */
  occupy(pointId: string, memberId: string): void {
    const point = this.seats.find(s => s.id === pointId)
    if (point) {
      point.occupied = true
      point.occupantId = memberId
    }
  }

  /** Release an occupied point. */
  release(pointId: string): void {
    const point = this.seats.find(s => s.id === pointId)
    if (point) {
      point.occupied = false
      point.occupantId = undefined
    }
  }

  /** Clear all seats (for rebuild). */
  clearSeats(): void {
    this.seats = []
  }

  // ─── Tree Positions ───────────────────────────

  /** Compute positions for N repo trees in the orchard zone. Delegates
   *  to `@shared/world/treePositions` so client + server agree. */
  getTreePositions(count: number): Array<{ x: number; z: number }> {
    return sharedGetTreePositions(count)
  }

  /** Reset layout for rebuild. */
  reset(): void {
    this.clearExclusionZones()
    this.clearSeats()
  }
}
