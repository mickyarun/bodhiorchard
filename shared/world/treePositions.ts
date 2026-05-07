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
 * All numeric tuning lives in `shared/world/layoutScale.ts` (the
 * `agentSlot` and `treeRingFormula` blocks) so this file is pure algorithm.
 *
 * Layout:
 *   - ≤8 trees   : single 270° arc at `orchardRadius * arcRadiusFactor`
 *   - >8 trees   : multi-ring spiral, rings growing outward from
 *                  `orchardRadius * innerRingFactor`
 */

import { ZONES, getZone, type Zone } from './zones'
import { getActiveScale } from './layoutScale'

/** Resolve the orchard zone or fail loudly — missing zone is a config bug. */
function requireOrchard(): Zone {
  const orchard = getZone('orchard')
  if (!orchard) throw new Error("zones.ts is missing the 'orchard' zone")
  return orchard
}

/**
 * World-space slot for an agent standing at a repo tree.
 *
 * Layout: arc on the hub-facing side of the tree. Slot 0 is the inward
 * radial (between tree and orchard center); additional slots fan
 * symmetrically ±slotAngleStepRad, wrapping to a second ring at ringStep
 * further out once slotsPerRing is reached. Scales to N agents per tree
 * without overflowing into path space.
 *
 * Used by:
 *   - `multiplayer/src/sim/AgentActivitySim.ts` — authoritative placement
 *   - `frontend/src/engine/agents/AgentCharacterSystem.ts` — legacy fallback
 *
 * Both sides MUST agree byte-for-byte; this is the single source of truth.
 *
 * @throws if `tree` coincides with the orchard center (degenerate radial).
 */
export function getAgentSlotAtTree(
  tree: { x: number; z: number },
  stackIndex = 0,
): { x: number; z: number } {
  const { agentSlot } = getActiveScale()
  const orchard = requireOrchard()
  const dx = orchard.x - tree.x
  const dz = orchard.z - tree.z
  const dist = Math.sqrt(dx * dx + dz * dz)
  if (dist === 0) {
    throw new Error('tree cannot coincide with the orchard center')
  }
  const rx = dx / dist
  const rz = dz / dist

  // Map stackIndex → (ring, angle). Slots alternate ±: 0, +1, -1, +2, -2 …
  const ring = Math.floor(stackIndex / agentSlot.slotsPerRing)
  const slotInRing = stackIndex % agentSlot.slotsPerRing
  const sign = slotInRing === 0 ? 0 : slotInRing % 2 === 1 ? 1 : -1
  const magnitude = Math.ceil(slotInRing / 2)
  const angle = sign * magnitude * agentSlot.slotAngleStepRad

  const radius = agentSlot.treeOffset + ring * agentSlot.ringStep
  const cos = Math.cos(angle)
  const sin = Math.sin(angle)
  const ax = rx * cos - rz * sin
  const az = rx * sin + rz * cos

  return {
    x: tree.x + ax * radius,
    z: tree.z + az * radius,
  }
}

/**
 * Open direction from orchard center — the quadrant facing away from the
 * centroid of activity zones. Three evenly-spaced activities yield +z
 * today; with different zone layouts this adapts automatically.
 */
function openDirectionFromOrchard(orchard: Zone): { rx: number; rz: number } {
  let sumX = 0, sumZ = 0, n = 0
  for (const z of ZONES) {
    if (z.tier !== 'activity') continue
    sumX += z.x - orchard.x
    sumZ += z.z - orchard.z
    n++
  }
  // No activity zones → default +z; centroid ≈ origin → also +z (symmetric).
  if (n === 0) return { rx: 0, rz: 1 }
  const mag = Math.sqrt(sumX * sumX + sumZ * sumZ)
  if (mag < 1e-6) return { rx: 0, rz: 1 }
  return { rx: -sumX / mag, rz: -sumZ / mag }
}

/**
 * Slot for an agent whose event carried no resolvable repo name.
 *
 * Anchored near the bodhi tree at the orchard center — a small offset in
 * the direction *away from* activity-zone clusters so the agent reads as
 * "standing at the bodhi tree" without overlapping its trunk.
 *
 * Offset = `moundRadius + fallbackClearance` so the agent always parks
 * just beyond the mound collider's rim. The clearance is sized to exceed
 * a character's half-width so the robot never spawns inside the platform.
 */
export function getAgentFallbackSlot(): { x: number; z: number } {
  const { hub } = getActiveScale()
  const orchard = requireOrchard()
  const { rx, rz } = openDirectionFromOrchard(orchard)
  const offset = hub.moundRadius + hub.fallbackClearance
  return {
    x: orchard.x + rx * offset,
    z: orchard.z + rz * offset,
  }
}

/** Compute positions for N repo trees inside the orchard zone. */
export function getTreePositions(count: number): Array<{ x: number; z: number }> {
  const { treeRingFormula: f } = getActiveScale()
  const orchard = requireOrchard()
  const positions: Array<{ x: number; z: number }> = []

  if (count <= 8) {
    const arcRadius = orchard.radius * f.arcRadiusFactor
    for (let i = 0; i < count; i++) {
      const angle = (i / Math.max(count - 1, 1)) * f.arcSpanRad + f.arcStartRad
      positions.push({
        x: orchard.x + Math.cos(angle) * arcRadius,
        z: orchard.z + Math.sin(angle) * arcRadius,
      })
    }
  } else {
    const rings = Math.ceil(count / f.ringsDivisor)
    let placed = 0
    for (let ring = 0; ring < rings && placed < count; ring++) {
      const ringRadius =
        orchard.radius * f.innerRingFactor +
        (ring * orchard.radius * f.outerRingFactor) / rings
      const perRing = Math.min(f.perRingBase + ring * f.perRingGrowth, count - placed)
      for (let i = 0; i < perRing && placed < count; i++) {
        const angle = (i / perRing) * Math.PI * 2 + ring * f.ringRotationOffsetRad
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
