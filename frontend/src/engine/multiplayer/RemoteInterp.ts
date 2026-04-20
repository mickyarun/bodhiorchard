// SPDX-License-Identifier: AGPL-3.0-or-later
// Copyright (C) 2026 Arun Rajkumar

/**
 * RemoteInterp — shared transform interpolation helpers for networked entities.
 *
 * Multiple subsystems (CharacterSystem, VehicleSystem) render entities whose
 * authoritative state arrives at Colyseus's patch rate (~20Hz) while the
 * render loop runs at ~60Hz. Without interpolation, entities snap between
 * discrete snapshot poses — visually read as flicker / stutter.
 *
 * Design rule: **never read transforms back from the entity.** PlayCanvas's
 * anim component and parent transforms can write the same entity between
 * frames, so `entity.getPosition()` / `getEulerAngles()` are not a reliable
 * interpolation source. Each caller tracks its own `current*` state here,
 * lerps toward `target*`, and writes the result to the entity.
 */

/**
 * Per-frame interpolation factor at 60fps. Higher → snappier catch-up to
 * the server target; lower → more visual smoothing at the cost of extra
 * lag. Shared by CharacterSystem and VehicleSystem so a player and their
 * mounted horse move with identical dynamics.
 */
export const POSITION_LERP = 0.25

/**
 * Normalize a yaw delta (target − current, degrees) to the range [-180, 180)
 * so interpolation always takes the shortest arc around the circle.
 *
 * Example: 350° → 10° should traverse +20° forward, not −340° backward.
 * Uses a symmetric modulo form so the ±180° boundary has no CCW/CW bias.
 */
export function normalizeYawDelta(delta: number): number {
  return ((delta + 180) % 360 + 360) % 360 - 180
}

/** Axis-aligned pose sample. Consumed in-place by `lerpPose` to avoid GC. */
export interface PoseState {
  targetX: number
  targetY: number
  targetZ: number
  targetYaw: number
  currentX: number
  currentY: number
  currentZ: number
  currentYaw: number
}

/**
 * Advance a pose one interpolation step toward its target. Mutates `pose`
 * in place — no allocation. Yaw interpolation uses shortest-path.
 *
 * @param factor Lerp factor per tick in (0, 1]. Pass `POSITION_LERP` unless
 *               the caller has a specific reason to deviate.
 */
export function lerpPose(pose: PoseState, factor: number = POSITION_LERP): void {
  pose.currentX += (pose.targetX - pose.currentX) * factor
  pose.currentY += (pose.targetY - pose.currentY) * factor
  pose.currentZ += (pose.targetZ - pose.currentZ) * factor
  pose.currentYaw += normalizeYawDelta(pose.targetYaw - pose.currentYaw) * factor
}
