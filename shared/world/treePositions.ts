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

import { ZONES, getZone, type Zone } from './zones'

/**
 * Base radial distance from a tree at which an agent stands. Tuned to
 * approximate (tree-trunk radius + character half-width + a small gap)
 * so the robot visibly "stands at" the trunk without clipping it.
 */
const AGENT_TREE_OFFSET = 1.8
/**
 * Additional radial step per full ring. When a tree has more agents than
 * SLOTS_PER_RING can comfortably fan, the next ring sits one step outward.
 */
const AGENT_RING_STEP = 1.2
/**
 * Slots around the hub-facing hemisphere before pushing to the next ring.
 * 5 = [center, +step, -step, +2step, -2step] → ±80° spread from inward.
 */
const SLOTS_PER_RING = 5
/** Angular step between adjacent slots on an arc. ~40° keeps ≥1 unit gap. */
const SLOT_ANGLE_STEP_RAD = (40 * Math.PI) / 180
/**
 * Offset from orchard (bodhi tree) center for the repo-free fallback slot.
 * Small enough to read as "standing at the bodhi tree," large enough to
 * not clip its trunk/canopy.
 */
const FALLBACK_HUB_OFFSET = 2.2

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
 * symmetrically ±SLOT_ANGLE_STEP_RAD, wrapping to a second ring at
 * AGENT_RING_STEP further out once SLOTS_PER_RING is reached. Scales
 * to N agents per tree without overflowing into path space.
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
  const ring = Math.floor(stackIndex / SLOTS_PER_RING)
  const slotInRing = stackIndex % SLOTS_PER_RING
  const sign = slotInRing === 0 ? 0 : slotInRing % 2 === 1 ? 1 : -1
  const magnitude = Math.ceil(slotInRing / 2)
  const angle = sign * magnitude * SLOT_ANGLE_STEP_RAD

  const radius = AGENT_TREE_OFFSET + ring * AGENT_RING_STEP
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
 * Anchored near the bodhi tree at the orchard center — a small offset
 * in the direction *away from* activity-zone clusters so the agent
 * reads as "standing at the bodhi tree" without overlapping its trunk.
 */
export function getAgentFallbackSlot(): { x: number; z: number } {
  const orchard = requireOrchard()
  const { rx, rz } = openDirectionFromOrchard(orchard)
  return {
    x: orchard.x + rx * FALLBACK_HUB_OFFSET,
    z: orchard.z + rz * FALLBACK_HUB_OFFSET,
  }
}

/** Compute positions for N repo trees inside the orchard zone. */
export function getTreePositions(count: number): Array<{ x: number; z: number }> {
  const orchard = requireOrchard()
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
