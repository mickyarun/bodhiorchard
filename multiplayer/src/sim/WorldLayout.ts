/**
 * WorldLayout — Shared layout data mirrored from frontend.
 *
 * Must match:
 *   - `frontend/src/engine/world/WorldLayout.ts` — ZONES
 *   - `frontend/src/engine/buildings/VillageLayout.ts` — house placement algorithm
 *
 * Used by the server to compute initial member placement without rendering.
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

// ─── VillageLayout constants (mirror frontend/src/engine/buildings/VillageLayout.ts) ───

const HOUSE_SPACING_ALONG = 5.5
const ROW_OFFSET = 6
const STREET_GAP = 18
const HOUSES_PER_SIDE = 4
const HOUSES_PER_STREET = HOUSES_PER_SIDE * 2

/**
 * Desk/bed offsets per house tier (corner-local space, before centering + rotation).
 * These match HouseBuilder's layout methods (corner origin at 0,0).
 */
const TIER_DESK: Record<number, { x: number; z: number; yaw: number }> = {
  1: { x: 2.2, z: 1.3, yaw: 180 },
  2: { x: 3.2, z: 1.3, yaw: 180 },
  3: { x: 3.4, z: 1.3, yaw: 180 },
}
const TIER_BED: Record<number, { x: number; z: number }> = {
  1: { x: 1.0, z: 0.7 },
  2: { x: 1.0, z: 1.1 },
  3: { x: 1.5, z: 0.8 },
}

/**
 * Centering offset per tier — shifts from corner-origin to center-origin.
 * Must match frontend HousingVillage.wrapWithPivot(), which now uses
 * (-tierDef.width/2, -tierDef.depth/2) uniformly because KayKit exteriors
 * are scaled at build time to fit the same tile footprint as the interior.
 *
 * Derived from HouseTierConfig: { 1: 3×3, 2: 4×4, 3: 5×5 }
 */
const TIER_CENTER_OFFSET: Record<number, { x: number; z: number }> = {
  1: { x: -1.5, z: -1.5 },   // 3×3 / 2
  2: { x: -2.0, z: -2.0 },   // 4×4 / 2
  3: { x: -2.5, z: -2.5 },   // 5×5 / 2
}

/**
 * Compute the world-space position and rotation of a member's house.
 * Mirrors frontend VillageLayout.computeVillageLayout() exactly.
 * One road per street, houses on both sides facing inward.
 */
export function getHouseOrigin(
  memberIndex: number,
  totalMembers: number,
): { x: number; z: number; yawDeg: number } | null {
  const zone = getZone("housing")
  if (!zone || totalMembers === 0) return null

  const streetCount = Math.max(1, Math.ceil(totalMembers / HOUSES_PER_STREET))
  const totalDepth = (streetCount - 1) * STREET_GAP
  const baseZ = zone.z - totalDepth / 2

  const streetIdx = Math.floor(memberIndex / HOUSES_PER_STREET)
  const posInStreet = memberIndex % HOUSES_PER_STREET
  const streetStart = streetIdx * HOUSES_PER_STREET
  const membersOnStreet = Math.min(HOUSES_PER_STREET, totalMembers - streetStart)

  // Determine side
  let side: 'north' | 'south'
  if (membersOnStreet <= HOUSES_PER_SIDE) {
    side = 'north'
  } else {
    side = posInStreet % 2 === 0 ? 'north' : 'south'
  }

  // Count per side for X layout
  let northCount = 0, southCount = 0
  for (let i = streetStart; i < streetStart + membersOnStreet; i++) {
    const pos = i % HOUSES_PER_STREET
    if (membersOnStreet <= HOUSES_PER_SIDE) { northCount++ }
    else if (pos % 2 === 0) { northCount++ }
    else { southCount++ }
  }

  // Compute slot on this member's side
  let slotOnSide = 0
  for (let i = streetStart; i < memberIndex; i++) {
    const pos = i % HOUSES_PER_STREET
    const iSide = membersOnStreet <= HOUSES_PER_SIDE ? 'north' : (pos % 2 === 0 ? 'north' : 'south')
    if (iSide === side) slotOnSide++
  }

  const streetZ = baseZ + streetIdx * STREET_GAP
  const maxPerSide = Math.max(northCount, southCount)
  const rowWidth = (maxPerSide - 1) * HOUSE_SPACING_ALONG
  const startX = zone.x - rowWidth / 2

  return {
    x: startX + slotOnSide * HOUSE_SPACING_ALONG,
    z: side === 'north' ? streetZ - ROW_OFFSET : streetZ + ROW_OFFSET,
    yawDeg: side === 'north' ? 0 : 180,
  }
}

/**
 * Compute world-space desk seat position for a member's house.
 * Applies centering offset (corner → center) then house rotation.
 */
export function getHouseDeskSeat(
  memberIndex: number,
  totalMembers: number,
  houseLevel = 1,
): { x: number; y: number; z: number; yaw: number } | null {
  const origin = getHouseOrigin(memberIndex, totalMembers)
  if (!origin) return null

  const local = TIER_DESK[houseLevel] ?? TIER_DESK[1]
  const offset = TIER_CENTER_OFFSET[houseLevel] ?? TIER_CENTER_OFFSET[1]
  // Shift from corner-local to center-local, then rotate
  const cx = offset.x + local.x
  const cz = offset.z + local.z
  const rad = origin.yawDeg * Math.PI / 180
  const cos = Math.cos(rad)
  const sin = Math.sin(rad)

  return {
    x: origin.x + cx * cos + cz * sin,
    y: 0,
    z: origin.z - cx * sin + cz * cos,
    yaw: local.yaw + origin.yawDeg,
  }
}

/**
 * Compute world-space bed position for a member's house.
 * Applies centering offset (corner → center) then house rotation.
 */
export function getHouseBedPosition(
  memberIndex: number,
  totalMembers: number,
  houseLevel = 1,
): { x: number; y: number; z: number; yaw: number } | null {
  const origin = getHouseOrigin(memberIndex, totalMembers)
  if (!origin) return null

  const local = TIER_BED[houseLevel] ?? TIER_BED[1]
  const offset = TIER_CENTER_OFFSET[houseLevel] ?? TIER_CENTER_OFFSET[1]
  const cx = offset.x + local.x
  const cz = offset.z + local.z
  const rad = origin.yawDeg * Math.PI / 180
  const cos = Math.cos(rad)
  const sin = Math.sin(rad)

  return {
    x: origin.x + cx * cos + cz * sin,
    y: 0.38,
    z: origin.z - cx * sin + cz * cos,
    yaw: origin.yawDeg,
  }
}

// ─── Tree positions (repo trees in orchard) ─────

export function getTreePositions(count: number): Array<{ x: number; z: number }> {
  const orchard = getZone("orchard")
  if (!orchard) return []
  const positions: Array<{ x: number; z: number }> = []

  if (count <= 8) {
    const arcRadius = orchard.radius * 0.65
    for (let i = 0; i < count; i++) {
      const angle = (i / Math.max(count - 1, 1)) * Math.PI * 1.5 - Math.PI * 0.75
      positions.push({
        x: orchard.x + Math.cos(angle) * arcRadius,
        z: orchard.z + Math.sin(angle) * arcRadius,
      })
    }
  } else {
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

// Break zone seats are now generated dynamically by BreakSeatGenerator.ts
// based on team size. See generateBreakSeats(teamSize) for the layout
// engines that mirror the frontend builders' exact furniture positions.
