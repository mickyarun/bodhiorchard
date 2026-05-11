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

import { describe, it, expect } from 'vitest'
import { computeVillageLayout } from '@shared/world/VillageLayout'
import type { Zone } from '@shared/world/zones'

const mockMembers = (n: number) =>
  Array.from({ length: n }, (_, i) => ({ user_id: `u${i}`, name: `User ${i}` }))

const baseZone: Zone = {
  name: 'housing', tier: 'habitation',
  x: -44, z: 52, radius: 14,
}

describe('computeVillageLayout', () => {
  it('returns zero outerReach and empty placements for no members', () => {
    const result = computeVillageLayout([], baseZone)
    expect(result.placements).toHaveLength(0)
    expect(result.outerReach).toBe(0)
    expect(result.center).toEqual({ x: -44, z: 52 })
  })

  it('emits placements in LOCAL coords (centred on 0,0)', () => {
    const result = computeVillageLayout(mockMembers(4), baseZone)
    // 4 members => 1 street, all north => symmetric around local x=0.
    const xs = result.placements.map(p => p.x)
    expect(Math.min(...xs) + Math.max(...xs)).toBeCloseTo(0, 5)
    // Local coords: far from the world zone centre (-44, 52).
    for (const p of result.placements) {
      expect(Math.abs(p.x)).toBeLessThan(20)
      expect(Math.abs(p.z)).toBeLessThan(20)
    }
  })

  it('outerReach grows with member count (more streets → farther corners)', () => {
    const r8  = computeVillageLayout(mockMembers(8),  baseZone).outerReach
    const r20 = computeVillageLayout(mockMembers(20), baseZone).outerReach
    expect(r20).toBeGreaterThan(r8)
  })

  it('applying a non-zero yaw changes outerReach vs the zero-yaw case', () => {
    const axis = computeVillageLayout(mockMembers(20), { ...baseZone, yawDeg: 0 }).outerReach
    const rot  = computeVillageLayout(mockMembers(20), { ...baseZone, yawDeg: -25 }).outerReach
    // Rotation around the zone centre moves each corner to a different
    // distance from world origin; the two values should not be identical.
    // The sign of the difference depends on zone position, so just assert
    // the computation is yaw-aware (not literally the same number).
    expect(Math.abs(rot - axis)).toBeGreaterThan(0.01)
  })

  it('fenceBounds sits in zone-local space (nowhere near world zone centre)', () => {
    const { fenceBounds } = computeVillageLayout(mockMembers(12), baseZone)
    const cx = (fenceBounds.minX + fenceBounds.maxX) / 2
    const cz = (fenceBounds.minZ + fenceBounds.maxZ) / 2
    // If bounds were accidentally computed in WORLD space they'd sit near
    // the zone centre (-44, 52). Local-space bounds stay within ±30 of origin.
    expect(Math.abs(cx)).toBeLessThan(20)
    expect(Math.abs(cz)).toBeLessThan(20)
  })

  it('is count-pure: identical results for same count, different member ids', () => {
    const a = computeVillageLayout(mockMembers(12), baseZone)
    const b = computeVillageLayout(
      Array.from({ length: 12 }, (_, i) => ({ user_id: `other${i}`, name: 'Z' })),
      baseZone,
    )
    expect(a.outerReach).toBeCloseTo(b.outerReach, 6)
    expect(a.fenceBounds).toEqual(b.fenceBounds)
    // Position-wise too: coordinates are the same even though ids differ.
    const posA = a.placements.map(p => `${p.x.toFixed(3)}|${p.z.toFixed(3)}|${p.yawDeg}`)
    const posB = b.placements.map(p => `${p.x.toFixed(3)}|${p.z.toFixed(3)}|${p.yawDeg}`)
    expect(posA).toEqual(posB)
  })
})
