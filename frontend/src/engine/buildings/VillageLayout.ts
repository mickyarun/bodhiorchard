// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * VillageLayout — Pure layout algorithm for village housing.
 *
 * One central road per street. Houses on both sides facing inward.
 * Multiple parallel streets for larger orgs (9+ members).
 *
 * Zero PlayCanvas imports — independently testable.
 *
 * Layout (top-down, +Z = south):
 *
 *   ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐     north side (yaw=0, doors face +Z)
 *   │ H0  │  │ H2  │  │ H4  │  │ H6  │
 *   └──┬──┘  └──┬──┘  └──┬──┘  └──┬──┘
 *   ═══╧════════╧════════╧════════╧═══════   ONE road (along X)
 *   ┌──┴──┐  ┌──┴──┐  ┌──┴──┐  ┌──┴──┐
 *   │ H1  │  │ H3  │  │ H5  │  │ H7  │
 *   └─────┘  └─────┘  └─────┘  └─────┘     south side (yaw=180, doors face -Z)
 *
 * Assignment: even index → north, odd → south (interleaved).
 * For ≤4 members (single side fits): all go north.
 * For 9+: wraps to a second parallel street.
 */

// ─── Layout Constants ────────────────────────────

/** Spacing between house origins along a street (X direction). */
export const HOUSE_SPACING_ALONG = 5.5

/** Z distance from road centerline to house origin. Must leave room for doors + walking. */
export const ROW_OFFSET = 6

/** Z distance between parallel street centerlines. */
export const STREET_GAP = 18

/** Max houses per side of one street. */
export const HOUSES_PER_SIDE = 4

/** Max houses per street (both sides combined). */
const HOUSES_PER_STREET = HOUSES_PER_SIDE * 2

// ─── Types ───────────────────────────────────────

export interface VillageMember {
  user_id: string
  name: string
  house_level?: number
}

export interface VillagePlacement {
  memberId: string
  memberName: string
  tier: number
  x: number
  z: number
  /** 0 = doors face +Z (north side), 180 = doors face -Z (south side). */
  yawDeg: number
  streetIndex: number
  side: 'north' | 'south'
  layoutIndex: number
}

export interface StreetDef {
  index: number
  /** Z coordinate of the road centerline. */
  centerZ: number
  startX: number
  endX: number
  northCount: number
  southCount: number
}

export interface FenceBounds {
  minX: number; maxX: number
  minZ: number; maxZ: number
}

export interface VillageLayoutResult {
  placements: VillagePlacement[]
  streets: StreetDef[]
  fenceRadius: number
  fenceBounds: FenceBounds
  /**
   * Distance from world origin (0, 0) to the furthest corner of `fenceBounds`.
   * Used by the outer campus perimeter so it grows to enclose the village
   * when the static `housing` zone radius in `shared/world/zones.ts` is
   * smaller than the member-count-driven village footprint.
   */
  outerReach: number
  center: { x: number; z: number }
}

// ─── Main Algorithm ──────────────────────────────

export function computeVillageLayout(
  members: VillageMember[],
  centerX: number,
  centerZ: number,
): VillageLayoutResult {
  const n = members.length
  if (n === 0) {
    return {
      placements: [], streets: [], fenceRadius: 5,
      fenceBounds: { minX: centerX - 5, maxX: centerX + 5, minZ: centerZ - 5, maxZ: centerZ + 5 },
      outerReach: 0,
      center: { x: centerX, z: centerZ },
    }
  }

  // ─── Step 1: Assign members to streets and sides ─────
  const streetCount = Math.max(1, Math.ceil(n / HOUSES_PER_STREET))
  const placements: VillagePlacement[] = []

  // Per-street counters
  const northCounts: number[] = new Array(streetCount).fill(0)
  const southCounts: number[] = new Array(streetCount).fill(0)

  for (let i = 0; i < n; i++) {
    const member = members[i]
    const streetIdx = Math.floor(i / HOUSES_PER_STREET)
    const posInStreet = i % HOUSES_PER_STREET

    // How many members are on this street?
    const streetStart = streetIdx * HOUSES_PER_STREET
    const membersOnStreet = Math.min(HOUSES_PER_STREET, n - streetStart)

    // If ≤ HOUSES_PER_SIDE: all north (single-sided). Otherwise interleave.
    let side: 'north' | 'south'
    if (membersOnStreet <= HOUSES_PER_SIDE) {
      side = 'north'
      northCounts[streetIdx]++
    } else if (posInStreet % 2 === 0) {
      side = 'north'
      northCounts[streetIdx]++
    } else {
      side = 'south'
      southCounts[streetIdx]++
    }

    placements.push({
      memberId: member.user_id,
      memberName: member.name,
      tier: member.house_level ?? 1,
      x: 0, z: 0,
      yawDeg: side === 'north' ? 0 : 180,
      streetIndex: streetIdx,
      side,
      layoutIndex: i,
    })
  }

  // ─── Step 2: Compute world positions ───────────────────
  const totalDepth = (streetCount - 1) * STREET_GAP
  const baseZ = centerZ - totalDepth / 2
  const streetDefs: StreetDef[] = []

  for (let s = 0; s < streetCount; s++) {
    const streetZ = baseZ + s * STREET_GAP
    const nc = northCounts[s]
    const sc = southCounts[s]
    const maxPerSide = Math.max(nc, sc)
    const rowWidth = (maxPerSide - 1) * HOUSE_SPACING_ALONG
    const startX = centerX - rowWidth / 2

    // Place north-side houses (above road)
    let northSlot = 0
    let southSlot = 0
    for (const p of placements) {
      if (p.streetIndex !== s) continue
      if (p.side === 'north') {
        p.x = startX + northSlot * HOUSE_SPACING_ALONG
        p.z = streetZ - ROW_OFFSET  // north of road
        northSlot++
      } else {
        p.x = startX + southSlot * HOUSE_SPACING_ALONG
        p.z = streetZ + ROW_OFFSET  // south of road
        southSlot++
      }
    }

    streetDefs.push({
      index: s,
      centerZ: streetZ,
      startX: startX - 2,
      endX: startX + rowWidth + 2,
      northCount: nc,
      southCount: sc,
    })
  }

  // ─── Step 3: Compute fence bounds (square, centered on layout) ──
  const HOUSE_EXTENT = 4 // max visual extent from house origin
  const PAD = 3          // breathing room around outermost houses
  let bMinX = Infinity, bMaxX = -Infinity
  let bMinZ = Infinity, bMaxZ = -Infinity
  for (const p of placements) {
    bMinX = Math.min(bMinX, p.x - HOUSE_EXTENT)
    bMaxX = Math.max(bMaxX, p.x + HOUSE_EXTENT)
    bMinZ = Math.min(bMinZ, p.z - HOUSE_EXTENT)
    bMaxZ = Math.max(bMaxZ, p.z + HOUSE_EXTENT)
  }
  // Square: expand the shorter dimension to match the longer one
  const cx = (bMinX + bMaxX) / 2
  const cz = (bMinZ + bMaxZ) / 2
  const halfExtent = Math.max((bMaxX - bMinX) / 2, (bMaxZ - bMinZ) / 2) + PAD
  const fenceBounds: FenceBounds = {
    minX: cx - halfExtent, maxX: cx + halfExtent,
    minZ: cz - halfExtent, maxZ: cz + halfExtent,
  }
  // Circular radius for backward compat (multiplayer WorldLayout.ts)
  const fenceRadius = halfExtent * Math.SQRT2

  // Max distance from world origin to any fence corner. Literal max over the
  // 4 corners rather than hypot(max|x|, max|z|) — the two agree when the
  // rectangle sits entirely in one quadrant (true for the current housing
  // zone at -30,40) but diverge if a future layout straddles the origin.
  const corners = [
    [fenceBounds.minX, fenceBounds.minZ],
    [fenceBounds.minX, fenceBounds.maxZ],
    [fenceBounds.maxX, fenceBounds.minZ],
    [fenceBounds.maxX, fenceBounds.maxZ],
  ] as const
  let outerReach = 0
  for (const [x, z] of corners) {
    const d = Math.hypot(x, z)
    if (d > outerReach) outerReach = d
  }

  return {
    placements,
    streets: streetDefs,
    fenceRadius: Math.max(fenceRadius, 8),
    fenceBounds,
    outerReach,
    center: { x: centerX, z: centerZ },
  }
}
