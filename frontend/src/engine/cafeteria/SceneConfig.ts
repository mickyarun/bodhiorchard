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
 * Cafeteria SceneConfig — layout constants for the cafeteria interior.
 *
 * The cafeteria interior is one GLB placed at the root entity's origin.
 * These constants live in the GLB's local coordinate space — they need to
 * be tuned once the GLB renders on-screen (see ARCHITECTURE.md notes on
 * GLB scale/origin).
 *
 * Starting estimates assume a ~8×6 m interior (measured roughly from the
 * fab.com preview). First in-browser test will surface whether the spawn
 * is inside geometry or floating — adjust here without changing code.
 */
import type { CollisionBox } from '../housetest/CollisionSystem'

/**
 * Uniform scale applied to the GLB geometry. The cafeteria.glb was authored
 * roughly 2× the scale of the KayKit character rig, so furniture dwarfs the
 * player at native scale. 0.5 brings chairs/tables to realistic proportion;
 * tune if the walls/floor look wrong.
 */
export const CAFETERIA_SCALE = 0.5

/** Interior room dimensions (metres), AFTER CAFETERIA_SCALE is applied.
 *  Native GLB bounds are 9.16×10.03 m. The walkable interior measured by
 *  walking the character into obstacles is tighter than the AABB: the
 *  counter at z≈1.29 and the big tables at z≈3.42 (both via HUD) plus the
 *  furthest vending machine leave room-depth just under 5 m. */
export const CAFETERIA_ROOM = {
  width: 4.0,
  depth: 5.0,
} as const

/** When true, CafeteriaScene renders every CollisionBox as a translucent
 *  red wireframe so interior obstacles can be positioned by eye. Flip on
 *  when re-tuning collision. */
export const CAFETERIA_DEBUG_COLLISION = false

/**
 * Rotation applied to the GLB so its "open side" faces +Z (the side the door
 * trigger lives on). Tune by 90° increments after first in-browser load.
 */
export const CAFETERIA_YAW = -180

/**
 * Vertical offset (metres) applied on top of the auto-`-min.y` recentering.
 * Positive = lowers the GLB; negative = raises it. The character spawns
 * at world y=0, so the walkable floor surface needs to land at y=0 too.
 *
 * Tuning log:
 *   0.0 → character only head visible
 *   1.5 → character standing on serving counter
 *   0.5 → small floating gap between feet and floor
 *   0.3 → candidate "on floor" — iterate from console log
 */
export const CAFETERIA_Y_OFFSET = 0.3

/** Where the player spawns after entering. Near the front door, facing the counter. */
export const CAFETERIA_SPAWN = { x: CAFETERIA_ROOM.width / 2, z: CAFETERIA_ROOM.depth - 1.2 } as const

/** Food counter approach position (player's side of the counter).
 *  Counter collision is (0.78–1.89, 0.94–1.57) — centre ≈ (1.3, 1.25);
 *  the approach point sits 0.6 m in front of the counter's south face. */
export const FOOD_COUNTER_POS = { x: 1.3, z: 1.9 } as const

/** Exit door position. Walking here triggers exit back to garden. */
export const EXIT_DOOR_POS = { x: CAFETERIA_ROOM.width / 2, z: CAFETERIA_ROOM.depth } as const

/**
 * Collision boxes for the cafeteria interior. The GLB has no collision
 * metadata, so we author AABBs by hand. Two groups:
 *
 *   1. Outer walls — keep the player inside the room footprint.
 *   2. Interior obstacles — counter, vending machines, tables. Positions
 *      are educated guesses from the GLB screenshots; enable
 *      CAFETERIA_DEBUG_COLLISION to render them as wireframes and tune.
 */
export const CAFETERIA_COLLISION: CollisionBox[] = [
  // ─── Outer walls ─────────────────────────────
  // Back wall (z=0)
  { minX: 0, maxX: CAFETERIA_ROOM.width, minZ: -0.1, maxZ: 0.2 },
  // Left wall (x=0)
  { minX: -0.1, maxX: 0.2, minZ: 0, maxZ: CAFETERIA_ROOM.depth },
  // Right wall (x=width)
  { minX: CAFETERIA_ROOM.width - 0.2, maxX: CAFETERIA_ROOM.width + 0.1, minZ: 0, maxZ: CAFETERIA_ROOM.depth },
  // Front wall split by central door opening
  { minX: 0, maxX: CAFETERIA_ROOM.width / 2 - 0.8, minZ: CAFETERIA_ROOM.depth - 0.2, maxZ: CAFETERIA_ROOM.depth + 0.1 },
  { minX: CAFETERIA_ROOM.width / 2 + 0.8, maxX: CAFETERIA_ROOM.width, minZ: CAFETERIA_ROOM.depth - 0.2, maxZ: CAFETERIA_ROOM.depth + 0.1 },

  // ─── Interior obstacles ──────────────────────
  // Authored from HUD touch circumnavigation. Raw touch AABB is shrunk by
  // PLAYER_RADIUS (0.28 m) on every side to get the real obstacle edges.

  // Serving counter — 14 touch points traced the perimeter; envelope
  // (0.50–2.17, 0.66–1.85) shrunk by 0.28 m gives this AABB.
  { minX: 0.78, maxX: 1.89, minZ: 0.94, maxZ: 1.57 },

  // 2-person table, right of counter — 17 touch points; envelope
  // (2.73–3.50, 1.54–2.79) shrunk by 0.28 m.
  { minX: 3.01, maxX: 3.22, minZ: 1.82, maxZ: 2.51 },

  // Produce / side table flush against the left wall — only 3 faces were
  // traceable (west face blocked by the wall), so minX snaps to the wall.
  { minX: 0.2, maxX: 1.05, minZ: 3.76, maxZ: 4.02 },

  // 4-person table, south-center — 11 touch points; envelope
  // (2.00–3.52, 3.50–4.35) shrunk by 0.28 m.
  { minX: 2.28, maxX: 3.24, minZ: 3.78, maxZ: 4.07 },
]
