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
 * CollisionSystem — Axis-Aligned Bounding Box slide collision.
 *
 * Tests X and Z independently so the player slides along walls
 * instead of stopping dead on contact (same technique as classic FPS engines).
 *
 * No physics engine required — purely mathematical position clamping.
 * Suitable for controlled demo environments with fixed furniture layouts.
 */
import * as pc from 'playcanvas'

/** Rectangular obstacle in the XZ plane. */
export interface CollisionBox {
  minX: number
  maxX: number
  minZ: number
  maxZ: number
}

/** Radius of the player's collision footprint (matches visual capsule width). */
export const PLAYER_RADIUS = 0.28

function overlaps(px: number, pz: number, b: CollisionBox): boolean {
  return (
    px > b.minX - PLAYER_RADIUS && px < b.maxX + PLAYER_RADIUS &&
    pz > b.minZ - PLAYER_RADIUS && pz < b.maxZ + PLAYER_RADIUS
  )
}

/**
 * Attempt to move a position by (dx, dz), respecting obstacles.
 * X and Z are tested independently — if X movement collides, only Z
 * is applied, allowing the player to slide along walls.
 *
 * Result is written into `out` (caller-supplied scratch Vec3) to avoid
 * per-frame heap allocation. Returns `out` for convenience.
 */
export function tryMove(
  pos: pc.Vec3,
  dx: number,
  dz: number,
  boxes: CollisionBox[],
  out: pc.Vec3,
): pc.Vec3 {
  const canX = !boxes.some(b => overlaps(pos.x + dx, pos.z, b))
  const canZ = !boxes.some(b => overlaps(pos.x, pos.z + dz, b))
  out.set(
    canX ? pos.x + dx : pos.x,
    pos.y,
    canZ ? pos.z + dz : pos.z,
  )
  return out
}
