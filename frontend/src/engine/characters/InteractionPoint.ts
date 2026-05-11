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
 * InteractionPoint — Where a character can sit, type, or interact.
 *
 * Replaces the old SeatSlot with:
 *   - Forward offset from furniture AABB center to actual seat surface
 *   - Per-furniture seat height (seatY)
 *   - Animation hint for the character at this point
 *   - Approach position for walk-to pathfinding (Step 3)
 *   - Occupancy tracking
 */

export type InteractionAnim = 'sit' | 'typing' | 'idle' | 'interact-right'

export interface InteractionPoint {
  id: string
  zone: string
  x: number
  y: number
  z: number
  yaw: number
  anim: InteractionAnim
  approachX: number
  approachZ: number
  occupied: boolean
  occupantId?: string
}

/**
 * Per-furniture seat surface offsets from AABB center.
 *
 * forwardOffset: how far forward (in the chair's facing direction) the seat
 *   surface is from the AABB center. The backrest shifts the AABB center
 *   backward; this corrects for it.
 * seatY: height of the seat surface above local floor level (Y=0 for most
 *   buildings). Derived from 50% of each model's AABB height (confirmed
 *   by debug calibration test). Pass baseY to createInteractionSeat for
 *   elevated floors like the pool resort.
 *
 * AABB heights measured from Kenney Furniture Kit GLBs:
 *   chairCushion: 0.460  →  seatY = 0.23
 *   chairDesk:    0.418  →  seatY = 0.21
 *   benchCushion: 0.460  →  seatY = 0.23
 *   loungeSofa:   0.460  →  seatY = 0.23
 *   loungeChair:  0.460  →  seatY = 0.23
 */
export const SEAT_OFFSETS: Record<string, { forwardOffset: number; seatY: number }> = {
  chairCushion:  { forwardOffset: 0.15, seatY: 0.23 },
  chairDesk:     { forwardOffset: 0.12, seatY: 0.21 },
  benchCushion:  { forwardOffset: 0.10, seatY: 0.23 },
  loungeSofa:    { forwardOffset: 0.08, seatY: 0.23 },
  loungeChair:   { forwardOffset: 0.10, seatY: 0.23 },
  pavilionBench: { forwardOffset: 0.10, seatY: 0.23 },
  poolChair:     { forwardOffset: 0, seatY: 0.25 },  // ProceduralBeachChair.SEAT_HEIGHT
}
