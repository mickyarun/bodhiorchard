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
 * Invariants of the shared village, break-seat and house-tier layouts that
 * both the engine and the multiplayer seat placement depend on.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { HOUSE_SPACING_ALONG, computeVillageLayout } from '@shared/world/VillageLayout'
import { BASELINE_REPO_COUNT, computeLayoutScale } from '@shared/world/layoutScale'
import { buildZones, type Zone } from '@shared/world/zones'
import { toWorld } from '@shared/world/geom'
import {
  CAFETERIA_LAYOUT,
  COFFEE_BAR_LAYOUT,
  breakSeatCount,
  forEachBreakSeat,
} from '@shared/world/breakSeats'
import { HOUSE_TIER_GEOMETRIES, getHouseTierGeometry } from '@shared/world/HouseTiers'

const MEMBER_COUNTS = [1, 2, 4, 8, 9, 16, 20, 25, 30]
/** Team sizes the housing position was sized for (zones.ts: 20-member design point). */
const DESIGNED_MEMBER_COUNTS = [1, 2, 4, 8, 9, 16, 20]
/** Safety margin between the village fence and the coffee bar (zones.ts doc). */
const VILLAGE_SAFETY_MARGIN = 4
const zones = buildZones(computeLayoutScale(BASELINE_REPO_COUNT))

function zone(name: string): Zone {
  const found = zones.find(z => z.name === name)
  if (!found) throw new Error(`zone ${name} missing`)
  return found
}

function members(n: number) {
  return Array.from({ length: n }, (_, i) => ({ user_id: `u${i}`, name: `User ${i}` }))
}

afterEach(() => {
  vi.restoreAllMocks()
})

describe('village layout', () => {
  it.each(MEMBER_COUNTS)('gives each of %i members their own plot', (n) => {
    const { placements } = computeVillageLayout(members(n), zone('housing'))
    expect(placements).toHaveLength(n)
    expect(new Set(placements.map(p => p.memberId)).size).toBe(n)
    for (let i = 0; i < placements.length; i++) {
      for (let j = i + 1; j < placements.length; j++) {
        const a = placements[i]!
        const b = placements[j]!
        expect(Math.hypot(a.x - b.x, a.z - b.z)).toBeGreaterThanOrEqual(HOUSE_SPACING_ALONG - 1e-9)
      }
    }
  })

  it.each(MEMBER_COUNTS)('keeps every house inside the fence for %i members', (n) => {
    const { placements, fenceBounds } = computeVillageLayout(members(n), zone('housing'))
    for (const p of placements) {
      expect(p.x).toBeGreaterThan(fenceBounds.minX)
      expect(p.x).toBeLessThan(fenceBounds.maxX)
      expect(p.z).toBeGreaterThan(fenceBounds.minZ)
      expect(p.z).toBeLessThan(fenceBounds.maxZ)
    }
  })

  it.each(DESIGNED_MEMBER_COUNTS)('keeps the fence clear of the coffee bar for %i members', (n) => {
    const housing = zone('housing')
    const coffee = zone('coffee_bar')
    const { fenceBounds } = computeVillageLayout(members(n), housing)
    // Coffee bar centre in the village's yaw-free local frame.
    const local = toWorld(
      { x: coffee.x - housing.x, z: coffee.z - housing.z },
      { x: 0, z: 0, yawDeg: -(housing.yawDeg ?? 0) },
    )
    const dx = Math.max(fenceBounds.minX - local.x, 0, local.x - fenceBounds.maxX)
    const dz = Math.max(fenceBounds.minZ - local.z, 0, local.z - fenceBounds.maxZ)
    const clearance = Math.hypot(dx, dz) - coffee.radius
    expect(clearance).toBeGreaterThanOrEqual(VILLAGE_SAFETY_MARGIN)
  })

  it('depends only on member order and count, not on names', () => {
    const a = computeVillageLayout(members(12), zone('housing'))
    const renamed = members(12).map(m => ({ ...m, name: `${m.name} renamed` }))
    const b = computeVillageLayout(renamed, zone('housing'))
    expect(b.placements.map(p => [p.x, p.z, p.yawDeg])).toEqual(
      a.placements.map(p => [p.x, p.z, p.yawDeg]),
    )
  })
})

describe('break seats', () => {
  it.each([COFFEE_BAR_LAYOUT, CAFETERIA_LAYOUT])('fit inside the $zone fence', (layout) => {
    const radius = zone(layout.zone).radius
    const seen = new Set<string>()
    const indices: number[] = []
    forEachBreakSeat(layout, (seatIndex, slot, chair) => {
      const x = slot.x + chair.dx
      const z = slot.z + chair.dz
      expect(Math.hypot(x, z)).toBeLessThan(radius)
      seen.add(`${x.toFixed(3)},${z.toFixed(3)}`)
      indices.push(seatIndex)
    })
    expect(indices).toEqual([...Array(breakSeatCount(layout)).keys()])
    expect(seen.size).toBe(breakSeatCount(layout))
  })
})

describe('house tiers', () => {
  it('declares tiers 1..N exactly once each', () => {
    const tiers = HOUSE_TIER_GEOMETRIES.map(t => t.tier)
    expect(tiers).toEqual([...Array(tiers.length).keys()].map(i => i + 1))
  })

  it.each([0, HOUSE_TIER_GEOMETRIES.length + 1, 1.5, Number.NaN, -1])('falls back to tier 1 for unknown tier %s', (tier) => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    expect(getHouseTierGeometry(tier)).toBe(HOUSE_TIER_GEOMETRIES[0])
    expect(warn).toHaveBeenCalledTimes(1)
  })

  it('returns the matching geometry for every declared tier', () => {
    for (const geometry of HOUSE_TIER_GEOMETRIES) {
      expect(getHouseTierGeometry(geometry.tier)).toBe(geometry)
    }
  })
})
