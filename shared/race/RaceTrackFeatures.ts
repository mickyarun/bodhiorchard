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
 * RaceTrackFeatures — boost pads + hurdles along the race track.
 *
 * Pure plain-data, like RacePhysics: consumed by the Colyseus server (the
 * authoritative simulation in RaceRoom) and by the frontend race scene
 * (which renders pads/hurdles at the same positions). Both sides derive
 * feature positions from the race distance through this module so the
 * visuals can never drift from the physics.
 *
 * Mechanics:
 *   - Boost pad: crossing one (first time only) opens `boostUntilMs` —
 *     a free speed window faster than a sprint, with no stamina drain.
 *   - Hurdle: crossing one outside an active jump window knocks the
 *     racer down — velocity zeroed, `knockdownUntilMs` opened, banked
 *     sprint/boost forfeited. They get up and re-accelerate from rest.
 *   - Jump: `triggerJump` opens `jumpUntilMs` for HURDLE_JUMP_WINDOW_MS,
 *     rate-limited by HURDLE_JUMP_COOLDOWN_MS between jump starts.
 */

import {
  BOOST_PAD_FRACTIONS,
  BOOST_DURATION_MS,
  HURDLE_FRACTIONS,
  HURDLE_JUMP_COOLDOWN_MS,
  HURDLE_JUMP_WINDOW_MS,
  HURDLE_KNOCKDOWN_MS,
} from './RaceConstants'
import type { Racer } from './RacePhysics'

/** Boost-pad centre positions (metres from the start line) for a track. */
export function boostPadPositionsM(trackLengthM: number): number[] {
  return BOOST_PAD_FRACTIONS.map((f) => f * trackLengthM)
}

/** Hurdle centre positions (metres from the start line) for a track. */
export function hurdlePositionsM(trackLengthM: number): number[] {
  return HURDLE_FRACTIONS.map((f) => f * trackLengthM)
}

/**
 * Register a jump-key tap. Opens the airborne window unless a previous
 * jump started less than HURDLE_JUMP_COOLDOWN_MS ago, or the racer is
 * currently on the ground after a knockdown. `lastJumpMs` is initialised
 * to -HURDLE_JUMP_COOLDOWN_MS in makeRacer so the first tap of a race is
 * always honoured.
 */
export function triggerJump(racer: Racer, nowMs: number): void {
  if (racer.finished) return
  if (isKnockedDown(racer, nowMs)) return
  if (nowMs < racer.lastJumpMs + HURDLE_JUMP_COOLDOWN_MS) return
  racer.lastJumpMs = nowMs
  racer.jumpUntilMs = nowMs + HURDLE_JUMP_WINDOW_MS
}

/** Is this racer currently inside a boost window? */
export function isBoosted(racer: Racer, nowMs: number): boolean {
  return nowMs < racer.boostUntilMs
}

/** Is this racer currently on the ground after hitting a hurdle? */
export function isKnockedDown(racer: Racer, nowMs: number): boolean {
  return nowMs < racer.knockdownUntilMs
}

/**
 * Apply boost-pad and hurdle crossings for the segment a racer covered
 * this tick: (prevPositionM, positionM]. Called by RacePhysics.tick after
 * position integration, only for racers that haven't finished.
 *
 * Each pad fires at most once per racer per race (tracked by bit in
 * `boostPadsHit`). Hurdles need no such latch — position is monotonically
 * non-decreasing, so each hurdle is crossed exactly once.
 */
export function stepTrackFeatures(
  racer: Racer,
  prevPositionM: number,
  nowMs: number,
  trackLengthM: number,
): void {
  const pads = boostPadPositionsM(trackLengthM)
  for (let i = 0; i < pads.length; i++) {
    const padBit = 1 << i
    if ((racer.boostPadsHit & padBit) !== 0) continue
    if (!crossed(prevPositionM, racer.positionM, pads[i])) continue
    racer.boostPadsHit |= padBit
    racer.boostUntilMs = nowMs + BOOST_DURATION_MS
  }

  const hurdles = hurdlePositionsM(trackLengthM)
  for (const hurdleM of hurdles) {
    if (!crossed(prevPositionM, racer.positionM, hurdleM)) continue
    if (nowMs < racer.jumpUntilMs) continue // airborne — clean clearance
    applyHurdleKnockdown(racer, nowMs)
  }
}

/** Did the segment (prevM, nextM] cross featureM? */
function crossed(prevM: number, nextM: number, featureM: number): boolean {
  return prevM < featureM && nextM >= featureM
}

/**
 * Penalty for hitting a hurdle: the racer falls — velocity zeroed on the
 * spot, knocked down for HURDLE_KNOCKDOWN_MS (no sprinting / jumping
 * while on the ground), and any banked sprint or boost window forfeited
 * (clamped to now, never extended). Speed is rebuilt from rest after the
 * get-up.
 */
function applyHurdleKnockdown(racer: Racer, nowMs: number): void {
  racer.velocityMps = 0
  racer.knockdownUntilMs = nowMs + HURDLE_KNOCKDOWN_MS
  racer.sprintUntilMs = Math.min(racer.sprintUntilMs, nowMs)
  racer.boostUntilMs = Math.min(racer.boostUntilMs, nowMs)
}
