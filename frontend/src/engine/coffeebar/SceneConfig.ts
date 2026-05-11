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
 * CoffeeBar SceneConfig — layout constants for the coffee bar interior.
 *
 * Interior is a single 5×5 room — matches the enlarged exterior hut. Door is
 * on the front (z=depth) at index 2 (center of 5).
 */
import type { CollisionBox } from '../housetest/CollisionSystem'

/** Room dimensions (in tile units). Matches the exterior hut. */
export const COFFEE_ROOM = {
  width: 5,
  depth: 5,
  doorIndex: 2,
} as const

/** Where the player spawns after entering. Clear of machine + queue markers. */
export const COFFEE_SPAWN = { x: 2.5, z: 4.0 } as const

/**
 * World-space x of the coffee machine — the single source of truth shared by:
 *   - CoffeeBarLayout.ts (visual placement of the machine GLB)
 *   - CoffeeBarBrewVisual.ts (cup + pour stream alignment)
 *   - CoffeeBarInteractionLoop.ts (player proximity check)
 *   - CharacterRoleAssigner / CoffeeBarRoom (NPC barista approach point)
 *
 * `z` is the player approach position in front of the counter, NOT the
 * machine's visual z (the GLB sits on the counter back). Keeping these
 * separated avoids the need for two near-identical constants.
 */
export const COFFEE_MACHINE_POS = { x: 3.0, z: 0.9 } as const

/**
 * Queue marker positions on the floor. Index 0 is "next up" at the machine,
 * subsequent indices trail back toward the door. Players/NPCs in the queue
 * are rendered at these positions.
 */
export const QUEUE_MARKERS: ReadonlyArray<{ x: number; z: number }> = [
  { x: 2.5, z: 1.7 },
  { x: 2.5, z: 2.4 },
  { x: 2.5, z: 3.1 },
  { x: 2.5, z: 3.8 },
]

/**
 * Static collision boxes for the 5×5 coffee bar interior.
 * Matches the wall layout produced by createWalls: 5-wide room with a single
 * door opening at front index=2.
 */
export const COFFEE_COLLISION: CollisionBox[] = [
  // Back wall
  { minX: 0, maxX: 5, minZ: -0.1, maxZ: 0.2 },
  // Left wall
  { minX: -0.1, maxX: 0.2, minZ: 0, maxZ: 5 },
  // Right wall
  { minX: 4.8, maxX: 5.1, minZ: 0, maxZ: 5 },
  // Front wall split by door opening at index=2 (tile x=2..3)
  { minX: 0, maxX: 2, minZ: 4.8, maxZ: 5.1 },
  { minX: 3, maxX: 5, minZ: 4.8, maxZ: 5.1 },
  // Bar counter — machine sits on top; counter blocks movement at z≈0.7.
  // X-bounds match the shrunken counter (left edge cleared so the wall menu
  // is visible above the empty left third of the back wall).
  { minX: 1.85, maxX: 4.5, minZ: 0.35, maxZ: 1.05 },
]
