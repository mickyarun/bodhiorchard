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
 * ForceSimulator — force-directed layout engine (pure math, zero PlayCanvas deps).
 *
 * Physics model:
 *   1. Repulsion  — all node pairs push apart (Coulomb's law)
 *   2. Attraction — edges pull connected nodes toward ideal length (Hooke's law)
 *   3. Centering  — gentle pull toward origin to prevent drift
 *   4. Collision  — push overlapping heavy nodes (repos) apart
 *   5. Damping    — velocity decays each step for stability
 *   6. Alpha      — global cooling factor; simulation settles when alpha < threshold
 */

// ─── Public Interfaces ─────────────────────────

export interface ForceNode {
  id: string
  x: number
  y: number
  z: number
  vx: number
  vy: number
  vz: number
  mass: number
  pinned: boolean
  /** Whether this node participates in collision detection. */
  collides: boolean
}

export interface ForceEdge {
  source: string
  target: string
  length: number
}

// ─── Tunable Constants ─────────────────────────

const REPULSION_STRENGTH = 200
const ATTRACTION_STRENGTH = 0.08
const CENTER_STRENGTH = 0.003
const DAMPING = 0.78
const ALPHA_DECAY = 0.003
const ALPHA_MIN = 0.001
const MAX_FORCE = 20
const MAX_REPULSION_DIST = 80
const CENTER_Y = 0  // center of the 3D space
// Minimum distance between heavy nodes (repos) — collision detection
const COLLISION_RADIUS = 12

// ─── Simulator ─────────────────────────────────

export class ForceSimulator {
  private _nodes: ForceNode[] = []
  private _edges: ForceEdge[] = []
  private alpha = 1.0
  private nodeIndex = new Map<string, number>()

  constructor(nodes: ForceNode[], edges: ForceEdge[]) {
    this._nodes = nodes
    this._edges = edges
    this.rebuildIndex()
  }

  /** Read-only access to nodes. */
  get nodes(): readonly ForceNode[] { return this._nodes }

  /** Read-only access to edges. */
  get edges(): readonly ForceEdge[] { return this._edges }

  private rebuildIndex(): void {
    this.nodeIndex.clear()
    for (let i = 0; i < this._nodes.length; i++) {
      this.nodeIndex.set(this._nodes[i].id, i)
    }
  }

  /** Run one simulation step. */
  step(dt: number): void {
    if (this.alpha < ALPHA_MIN) return

    // Normalize dt to avoid huge jumps (target 16ms frame)
    const tScale = Math.min(dt / 0.016, 3)

    // 1. Repulsion — all pairs
    const n = this._nodes.length
    for (let i = 0; i < n; i++) {
      const a = this._nodes[i]
      if (a.pinned) continue
      for (let j = i + 1; j < n; j++) {
        const b = this._nodes[j]

        const dx = a.x - b.x
        const dy = a.y - b.y
        const dz = a.z - b.z
        const distSq = dx * dx + dy * dy + dz * dz
        if (distSq > MAX_REPULSION_DIST * MAX_REPULSION_DIST) continue

        const dist = Math.sqrt(distSq) || 0.1
        const strength = REPULSION_STRENGTH * a.mass * b.mass
        let force = (strength / (distSq || 0.01)) * this.alpha
        force = Math.min(force, MAX_FORCE)

        const fx = (dx / dist) * force
        const fy = (dy / dist) * force
        const fz = (dz / dist) * force

        if (!a.pinned) { a.vx += fx / a.mass; a.vy += fy / a.mass; a.vz += fz / a.mass }
        if (!b.pinned) { b.vx -= fx / b.mass; b.vy -= fy / b.mass; b.vz -= fz / b.mass }
      }
    }

    // 2. Attraction — edges only
    for (const edge of this._edges) {
      const ai = this.nodeIndex.get(edge.source)
      const bi = this.nodeIndex.get(edge.target)
      if (ai === undefined || bi === undefined) continue

      const a = this._nodes[ai]
      const b = this._nodes[bi]

      const dx = b.x - a.x
      const dy = b.y - a.y
      const dz = b.z - a.z
      const dist = Math.sqrt(dx * dx + dy * dy + dz * dz) || 0.1
      const displacement = dist - edge.length
      const force = ATTRACTION_STRENGTH * displacement * this.alpha

      const fx = (dx / dist) * force
      const fy = (dy / dist) * force
      const fz = (dz / dist) * force

      if (!a.pinned) { a.vx += fx / a.mass; a.vy += fy / a.mass; a.vz += fz / a.mass }
      if (!b.pinned) { b.vx -= fx / b.mass; b.vy -= fy / b.mass; b.vz -= fz / b.mass }
    }

    // 3. Centering + damping + integrate
    for (const node of this._nodes) {
      if (node.pinned) continue

      // Centering force
      node.vx -= node.x * CENTER_STRENGTH * node.mass * this.alpha
      node.vy -= (node.y - CENTER_Y) * CENTER_STRENGTH * node.mass * this.alpha
      node.vz -= node.z * CENTER_STRENGTH * node.mass * this.alpha

      // Damping
      node.vx *= DAMPING
      node.vy *= DAMPING
      node.vz *= DAMPING

      // Integrate — full 3D, no Y clamp
      node.x += node.vx * tScale
      node.y += node.vy * tScale
      node.z += node.vz * tScale
    }

    // 4. Collision detection — push heavy nodes (repos) apart if overlapping
    for (let i = 0; i < n; i++) {
      const a = this._nodes[i]
      if (!a.collides) continue
      for (let j = i + 1; j < n; j++) {
        const b = this._nodes[j]
        if (!b.collides) continue

        const dx = b.x - a.x
        const dz = b.z - a.z
        const distXZ = Math.sqrt(dx * dx + dz * dz) || 0.1

        if (distXZ < COLLISION_RADIUS) {
          // Push apart to minimum distance
          const overlap = (COLLISION_RADIUS - distXZ) / 2
          const nx = dx / distXZ
          const nz = dz / distXZ

          if (!a.pinned) { a.x -= nx * overlap; a.z -= nz * overlap }
          if (!b.pinned) { b.x += nx * overlap; b.z += nz * overlap }
        }
      }
    }

    // 5. Alpha decay
    this.alpha *= (1 - ALPHA_DECAY)
  }

  /** True when the simulation has cooled below threshold. */
  isSettled(): boolean {
    return this.alpha < ALPHA_MIN
  }

  /** Run N steps instantly (for initial layout before first render). */
  warmup(iterations: number): void {
    for (let i = 0; i < iterations; i++) {
      this.step(0.016)
    }
  }

  /** Reheat the simulation (e.g. after data changes). */
  reheat(alpha = 0.5): void {
    this.alpha = alpha
  }

  /** Get a node by id. */
  getNode(id: string): ForceNode | undefined {
    const idx = this.nodeIndex.get(id)
    return idx !== undefined ? this._nodes[idx] : undefined
  }
}
