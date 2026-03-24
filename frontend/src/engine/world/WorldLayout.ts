/**
 * WorldLayout — Master layout: zone positions + exclusion zones + seat registry.
 *
 * Defines world zones as named circles. Every building/tree system
 * uses this to know WHERE to place things. Scatter systems (grass, rocks)
 * use the exclusion zones to avoid placing inside buildings.
 */
import type { ExclusionZone } from '../utils/MathUtils'
import type { InteractionPoint } from '../characters/InteractionPoint'

/** Backward-compatible alias — use InteractionPoint in new code. */
export type SeatSlot = InteractionPoint

// ─── Zone Definitions ───────────────────────────

export interface WorldZone {
  name: string
  x: number
  z: number
  radius: number
}

/** Fixed zone positions — spaced out for TILE_SIZE=1 with larger orchard. */
const ZONES: WorldZone[] = [
  { name: 'orchard',    x: 0,    z: 0,    radius: 22 },
  { name: 'coffee_bar', x: -28,  z: -20,  radius: 8 },
  { name: 'cafeteria',  x: 28,   z: -20,  radius: 9 },
  { name: 'housing',    x: -30,  z: 22,   radius: 14 },
  { name: 'pool',       x: 30,   z: 22,   radius: 10 },
  { name: 'pavilion',   x: 0,    z: -32,  radius: 6 },
]

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

  /**
   * Compute positions for N repo trees in an arc/grid layout
   * within the orchard zone.
   */
  getTreePositions(count: number): Array<{ x: number; z: number }> {
    const orchard = this.getZone('orchard')!
    const positions: Array<{ x: number; z: number }> = []

    if (count <= 8) {
      // Single arc for small counts — use most of the orchard radius for spacing
      const arcRadius = orchard.radius * 0.65
      for (let i = 0; i < count; i++) {
        const angle = (i / Math.max(count - 1, 1)) * Math.PI * 1.5 - Math.PI * 0.75
        positions.push({
          x: orchard.x + Math.cos(angle) * arcRadius,
          z: orchard.z + Math.sin(angle) * arcRadius,
        })
      }
    } else {
      // Multi-ring spiral for larger counts — wider spacing between rings
      const rings = Math.ceil(count / 6)
      let placed = 0
      for (let ring = 0; ring < rings && placed < count; ring++) {
        const ringRadius = orchard.radius * 0.3 + (ring * orchard.radius * 0.65) / rings
        const perRing = Math.min(6 + ring * 2, count - placed)
        for (let i = 0; i < perRing && placed < count; i++) {
          const angle = (i / perRing) * Math.PI * 2 + ring * 0.5
          positions.push({
            x: orchard.x + Math.cos(angle) * ringRadius,
            z: orchard.z + Math.sin(angle) * ringRadius,
          })
          placed++
        }
      }
    }

    return positions
  }

  /** Reset layout for rebuild. */
  reset(): void {
    this.clearExclusionZones()
    this.clearSeats()
  }
}
