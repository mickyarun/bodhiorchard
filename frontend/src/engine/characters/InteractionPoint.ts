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
  poolChair:     { forwardOffset: 0.05, seatY: 0.15 },
}
