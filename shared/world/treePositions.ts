// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * Shared repo-tree placement math.
 *
 * Imported by:
 *   - `frontend/src/engine/world/WorldLayout.ts` — positions rendered trees
 *   - `multiplayer/src/sim/WorldLayout.ts` — authoritative server placement
 *
 * Both sides MUST agree on tree positions (server owns per-tree identity
 * for ownership/interaction; client renders them). Drift here previously
 * required byte-for-byte copies of this function. Single implementation
 * eliminates that risk.
 *
 * Layout:
 *   - ≤8 trees   : single 270° arc at 65% of orchard radius
 *   - >8 trees   : multi-ring spiral, rings growing outward from 30% radius
 */

import { getZone } from './zones'

/** Compute positions for N repo trees inside the orchard zone. */
export function getTreePositions(count: number): Array<{ x: number; z: number }> {
  const orchard = getZone('orchard')
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
