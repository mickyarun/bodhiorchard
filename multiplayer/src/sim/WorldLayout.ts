/**
 * WorldLayout — Shared layout data mirrored from frontend WorldLayout.
 *
 * Must match `frontend/src/engine/world/WorldLayout.ts` ZONES and the
 * house grid layout in `frontend/src/engine/buildings/HousingVillage.ts`.
 *
 * Used by the server to compute initial member placement without needing
 * to actually render anything.
 */

export interface Zone {
  name: string
  x: number
  z: number
  radius: number
}

/** Mirror of frontend ZONES array. Keep in sync. */
export const ZONES: Zone[] = [
  { name: "orchard",    x: 0,    z: 0,    radius: 22 },
  { name: "coffee_bar", x: -28,  z: -20,  radius: 8 },
  { name: "cafeteria",  x: 28,   z: -20,  radius: 9 },
  { name: "housing",    x: -30,  z: 22,   radius: 14 },
  { name: "pool",       x: 30,   z: 22,   radius: 10 },
  { name: "pavilion",   x: 0,    z: -32,  radius: 6 },
]

/** Get a zone by name. */
export function getZone(name: string): Zone | null {
  return ZONES.find(z => z.name === name) ?? null
}

// ─── House grid layout ───────────────────────
// Mirror of HousingVillage constants

export const HOUSE_SPACING_X = 6
export const HOUSE_SPACING_Z = 6
export const HOUSES_PER_ROW = 4

/** Desk seat offset in house-local space (x=3.2, z=1.3 before rotation). */
const DESK_LOCAL_X = 3.2
const DESK_LOCAL_Z = 1.3
const DESK_YAW = 180  // faces -Z (before 90° house rotation)

/** Bed position in house-local space. */
const BED_LOCAL_X = 1.0
const BED_LOCAL_Z = 1.1

/**
 * Compute the world-space position of a member's house origin.
 * Houses are laid out in a grid centered on the housing zone.
 *
 * @param memberIndex - Index of this member in the members array (stable ordering)
 * @param totalMembers - Total number of members in the org
 */
export function getHouseOrigin(memberIndex: number, totalMembers: number): { x: number; z: number } | null {
  const zone = getZone("housing")
  if (!zone || totalMembers === 0) return null

  const cols = Math.min(HOUSES_PER_ROW, totalMembers)
  const rows = Math.ceil(totalMembers / cols)
  const totalWidth = (cols - 1) * HOUSE_SPACING_X
  const totalDepth = (rows - 1) * HOUSE_SPACING_Z

  const col = memberIndex % cols
  const row = Math.floor(memberIndex / cols)

  return {
    x: zone.x + col * HOUSE_SPACING_X - totalWidth / 2,
    z: zone.z + row * HOUSE_SPACING_Z - totalDepth / 2,
  }
}

/**
 * Compute world-space desk seat position for a member's house.
 * Applies the 90° Y rotation that HousingVillage applies to house entities:
 *   local (dx, dz) → world offset (dz, -dx)
 */
export function getHouseDeskSeat(
  memberIndex: number,
  totalMembers: number,
): { x: number; y: number; z: number; yaw: number } | null {
  const origin = getHouseOrigin(memberIndex, totalMembers)
  if (!origin) return null

  // Apply 90° rotation: (dx, dz) → (dz, -dx)
  const dx = DESK_LOCAL_X
  const dz = DESK_LOCAL_Z
  return {
    x: origin.x + dz,
    y: 0,
    z: origin.z - dx,
    yaw: DESK_YAW + 90,  // add 90° for house rotation
  }
}

/**
 * Compute world-space bed position for a member's house.
 * Same 90° rotation applied.
 */
export function getHouseBedPosition(
  memberIndex: number,
  totalMembers: number,
): { x: number; y: number; z: number; yaw: number } | null {
  const origin = getHouseOrigin(memberIndex, totalMembers)
  if (!origin) return null

  const dx = BED_LOCAL_X
  const dz = BED_LOCAL_Z
  return {
    x: origin.x + dz,
    y: 0.38,
    z: origin.z - dx,
    yaw: 90,
  }
}

// ─── Tree positions (repo trees in orchard) ─────
// Mirror of frontend WorldLayout.getTreePositions() so the server
// can compute tree positions without needing to render anything.

export function getTreePositions(count: number): Array<{ x: number; z: number }> {
  const orchard = getZone("orchard")
  if (!orchard) return []
  const positions: Array<{ x: number; z: number }> = []

  if (count <= 8) {
    // Single arc for small counts
    const arcRadius = orchard.radius * 0.65
    for (let i = 0; i < count; i++) {
      const angle = (i / Math.max(count - 1, 1)) * Math.PI * 1.5 - Math.PI * 0.75
      positions.push({
        x: orchard.x + Math.cos(angle) * arcRadius,
        z: orchard.z + Math.sin(angle) * arcRadius,
      })
    }
  } else {
    // Multi-ring spiral for larger counts
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

// ─── Break zone seats (coffee bar, pool) ─────

/**
 * Simplified break seat positions — approximate placements within break zones.
 * Multiple seats per zone allow round-robin assignment.
 */
export const BREAK_SEATS: Array<{ zone: string; x: number; y: number; z: number; yaw: number }> = [
  // Coffee bar seats (around zone x=-28, z=-20)
  { zone: "coffee_bar", x: -28, y: 0, z: -22, yaw: 0 },
  { zone: "coffee_bar", x: -26, y: 0, z: -20, yaw: 270 },
  { zone: "coffee_bar", x: -30, y: 0, z: -20, yaw: 90 },
  { zone: "coffee_bar", x: -28, y: 0, z: -18, yaw: 180 },

  // Pool seats (around zone x=30, z=22)
  { zone: "pool_resort", x: 30, y: 0, z: 20, yaw: 0 },
  { zone: "pool_resort", x: 32, y: 0, z: 22, yaw: 270 },
  { zone: "pool_resort", x: 28, y: 0, z: 22, yaw: 90 },
  { zone: "pool_resort", x: 30, y: 0, z: 24, yaw: 180 },
]
