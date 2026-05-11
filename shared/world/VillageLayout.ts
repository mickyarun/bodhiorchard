// Copyright 2025-2026 Arun Rajkumar
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * VillageLayout — Pure layout algorithm for village housing.
 *
 * Shared between frontend (rendering) and multiplayer (spawn math). Emits
 * placements in the village's ZONE-LOCAL frame (yaw-free, centred on 0,0).
 * Callers that need world coordinates rotate-and-translate by the housing
 * zone (`zone.x, zone.z, zone.yawDeg`) via `rotatePointAroundPivot` from
 * `./geom.ts`.
 *
 * Zero PlayCanvas imports — independently testable.
 *
 * Layout (top-down, +Z = south, before zone yaw):
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
 *
 * Placements are **count-pure**: they depend only on `members.length` and
 * the zone, never on member identity or ordering. The multiplayer memoisation
 * in `multiplayer/src/sim/WorldLayout.ts` relies on this invariant.
 */
import { rotatePointAroundPivot } from './geom'
import type { Zone } from './zones'

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
  /** House origin X in ZONE-LOCAL space (yaw-free). */
  x: number
  /** House origin Z in ZONE-LOCAL space. */
  z: number
  /** 0 = doors face +Z (north side), 180 = doors face -Z (south side). Local. */
  yawDeg: number
  streetIndex: number
  side: 'north' | 'south'
  layoutIndex: number
}

export interface StreetDef {
  index: number
  /** Z coordinate of the road centerline in ZONE-LOCAL space. */
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
  /** Placements in zone-LOCAL space (yaw-free, centred on 0,0). */
  placements: VillagePlacement[]
  /** Streets in zone-LOCAL space. */
  streets: StreetDef[]
  /** Maximum circular extent in LOCAL space. */
  fenceRadius: number
  /** Rectangle in zone-LOCAL space (axis-aligned, yaw-free). */
  fenceBounds: FenceBounds
  /**
   * Distance from world origin (0, 0) to the furthest rotated corner of
   * `fenceBounds` after the village yaw is applied. Drives the outer
   * campus perimeter so the rail encloses the true village footprint
   * even when yaw + member-count push the rectangle past the static
   * `housing.radius` in `shared/world/zones.ts`.
   */
  outerReach: number
  /** World-space centre of the village (= zone.x, zone.z). */
  center: { x: number; z: number }
  /** Zone yaw in radians — callers use this to convert placements to world. */
  yawRad: number
}

// ─── Main Algorithm ──────────────────────────────

export function computeVillageLayout(
  members: VillageMember[],
  zone: Zone,
): VillageLayoutResult {
  const n = members.length
  const yawRad = ((zone.yawDeg ?? 0) * Math.PI) / 180
  // Internal algorithm runs in LOCAL coordinates around (0, 0); callers
  // (frontend root entity / multiplayer wrapper) handle the world transform.

  if (n === 0) {
    return {
      placements: [], streets: [], fenceRadius: 5,
      fenceBounds: { minX: -5, maxX: 5, minZ: -5, maxZ: 5 },
      outerReach: 0,
      center: { x: zone.x, z: zone.z },
      yawRad,
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

  // ─── Step 2: Compute LOCAL positions (centred on 0,0) ───
  const totalDepth = (streetCount - 1) * STREET_GAP
  const baseZ = -totalDepth / 2
  const streetDefs: StreetDef[] = []

  for (let s = 0; s < streetCount; s++) {
    const streetZ = baseZ + s * STREET_GAP
    const nc = northCounts[s]
    const sc = southCounts[s]
    const maxPerSide = Math.max(nc, sc)
    const rowWidth = (maxPerSide - 1) * HOUSE_SPACING_ALONG
    const startX = -rowWidth / 2

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

  // ─── Step 3: Compute fence bounds (LOCAL, yaw-free) ──
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
  const fenceRadius = halfExtent * Math.SQRT2

  // World-space outer reach: rotate each LOCAL corner by the zone yaw around
  // the zone centre, then measure to world origin. Applying rotation here
  // (rather than leaving it to the consumer) means a future caller can't
  // silently compute an axis-aligned reach by forgetting to rotate.
  const localCorners = [
    { x: fenceBounds.minX, z: fenceBounds.minZ },
    { x: fenceBounds.minX, z: fenceBounds.maxZ },
    { x: fenceBounds.maxX, z: fenceBounds.minZ },
    { x: fenceBounds.maxX, z: fenceBounds.maxZ },
  ]
  let outerReach = 0
  for (const c of localCorners) {
    // rotate LOCAL corner into world by first translating to world centre,
    // then rotating around that centre.
    const w = rotatePointAroundPivot(c.x + zone.x, c.z + zone.z, yawRad, zone.x, zone.z)
    const d = Math.hypot(w.x, w.z)
    if (d > outerReach) outerReach = d
  }

  return {
    placements,
    streets: streetDefs,
    fenceRadius: Math.max(fenceRadius, 8),
    fenceBounds,
    outerReach,
    center: { x: zone.x, z: zone.z },
    yawRad,
  }
}
