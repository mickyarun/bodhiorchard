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
 * RaceTrackFeatures — boost pads + hurdles along the circuit loop.
 *
 * Pure plain-data, like RacePhysics: consumed by the Colyseus server (the
 * authoritative simulation in RaceRoom) and by the frontend race scene
 * (which renders pads/hurdles at the same positions). Both sides derive
 * feature positions from the fixed LOOP_LENGTH_M through this module so
 * the visuals can never drift from the physics.
 *
 * Loop-space firing: features live on the single physical loop at
 * fractions of LOOP_LENGTH_M. A racer's `positionM` is the cumulative arc
 * along the centreline, which on a multi-lap race exceeds LOOP_LENGTH_M.
 * Each tick we map the crossed segment (prevPositionM, positionM] into
 * loop-space (mod LOOP_LENGTH_M) and check the pad/hurdle fractions there,
 * so every feature fires exactly once on every lap it is crossed — no
 * per-race latch needed. Position is monotonically non-decreasing, so a
 * pad can't be crossed twice within one lap.
 *
 * Mechanics:
 *   - Boost pad: crossing one opens `boostUntilMs` — a free speed window
 *     faster than a sprint, with no stamina drain. Fires once per lap.
 *   - Hurdle: crossing one outside an active jump window knocks the
 *     racer down — velocity zeroed, `knockdownUntilMs` opened, banked
 *     sprint/boost forfeited. They get up and re-accelerate from rest.
 *     A physical bar is jumped (or clipped) every lap it's crossed.
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
  LOOP_LENGTH_M,
} from './RaceConstants'
import type { Racer } from './RacePhysics'

/**
 * Boost-pad centre positions (metres from the start line) on a loop of
 * the given length. Defaults to the fixed LOOP_LENGTH_M; callers placing
 * physical props pass LOOP_LENGTH_M explicitly to read at the call site.
 */
export function boostPadPositionsM(loopLengthM: number = LOOP_LENGTH_M): number[] {
  return BOOST_PAD_FRACTIONS.map((f) => f * loopLengthM)
}

/** Hurdle centre positions (metres from the start line) on the loop. */
export function hurdlePositionsM(loopLengthM: number = LOOP_LENGTH_M): number[] {
  return HURDLE_FRACTIONS.map((f) => f * loopLengthM)
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
 * Loop-space, per-lap: the crossed segment is reduced mod LOOP_LENGTH_M
 * and checked against the pad/hurdle fractions on the single physical
 * loop, so each feature fires once on every lap it's crossed. No latch is
 * needed — within a lap position is monotonic, so a feature can't fire
 * twice, and re-firing on the next lap is exactly the desired behaviour.
 *
 * A tick advances at most V_MAX_MPS·dt (≈0.6 m), far below LOOP_LENGTH_M,
 * so the segment spans the start line at most once. The wrap case
 * (loopPos < loopPrev) is split into (loopPrev, L] then (0, loopPos].
 */
export function stepTrackFeatures(racer: Racer, prevPositionM: number, nowMs: number): void {
  const loopPrev = prevPositionM % LOOP_LENGTH_M
  const loopPos = racer.positionM % LOOP_LENGTH_M
  // Segments to test in loop-space: one for a within-lap step, two when
  // the tick crossed the start line (loopPos wrapped below loopPrev).
  const segments: Array<[number, number]> =
    loopPos < loopPrev
      ? [
          [loopPrev, LOOP_LENGTH_M],
          [0, loopPos],
        ]
      : [[loopPrev, loopPos]]

  for (const padM of boostPadPositionsM()) {
    if (!crossedAnySegment(segments, padM)) continue
    racer.boostUntilMs = nowMs + BOOST_DURATION_MS
  }

  for (const hurdleM of hurdlePositionsM()) {
    if (!crossedAnySegment(segments, hurdleM)) continue
    if (nowMs < racer.jumpUntilMs) continue // airborne — clean clearance
    applyHurdleKnockdown(racer, nowMs)
  }
}

/** True if any loop-space segment (prevM, nextM] crosses featureM. */
function crossedAnySegment(segments: ReadonlyArray<[number, number]>, featureM: number): boolean {
  for (const [prevM, nextM] of segments) {
    if (crossed(prevM, nextM, featureM)) return true
  }
  return false
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
