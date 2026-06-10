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
 * RacePhysics — pure race mechanics.
 *
 * No PlayCanvas imports, no framework dependencies. Pure plain-data so
 * Phase 2 can hoist into a shared package consumed by both the client
 * (local mode) and the Colyseus server (live mode).
 *
 * Mechanic:
 *   - Holding a "move" key sets `isMoving = true`.
 *   - Tapping the sprint key extends `sprintUntilMs` by SPRINT_TAP_DURATION_MS,
 *     capped at SPRINT_MAX_WINDOW_MS above now. The racer is "sprinting"
 *     while `nowMs < sprintUntilMs`.
 *   - Each tick velocity accelerates toward:
 *       0                if knocked down (hurdle hit — on the ground)
 *       BOOST_TARGET_MPS if isMoving && boosted (pad window)
 *       RUN_TARGET_MPS   if isMoving && sprinting
 *       WALK_TARGET_MPS  if isMoving
 *       0                otherwise (decelerates toward rest)
 *   - Boost pads + hurdles along the track are applied per-tick by
 *     RaceTrackFeatures.stepTrackFeatures (see that module's contract).
 *
 * Integrates at the caller's dt so movement is frame-smooth.
 */

import {
  WALK_TARGET_MPS,
  RUN_TARGET_MPS,
  BOOST_TARGET_MPS,
  MOVE_ACCEL_MPSS,
  MOVE_DECEL_MPSS,
  SPRINT_TAP_DURATION_MS,
  SPRINT_MAX_WINDOW_MS,
  HURDLE_JUMP_COOLDOWN_MS,
  V_MAX_MPS,
  TRACK_LENGTH_M,
  STAMINA_MAX,
  STAMINA_INITIAL,
  SPRINT_DRAIN_PER_S,
  WALK_REGEN_PER_S,
  IDLE_REGEN_PER_S,
} from './RaceConstants'
import { isBoosted, isKnockedDown, stepTrackFeatures } from './RaceTrackFeatures'
import type { Placing } from './types'

/**
 * Mutable state for one racer. Constructed once per round and mutated in
 * place.
 */
export interface Racer {
  readonly id: string
  positionM: number
  velocityMps: number
  finished: boolean
  /** ms since race start when the racer first crossed the finish line. 0 if not finished. */
  finishTimeMs: number
  /** True while the player is holding their move key. */
  isMoving: boolean
  /**
   * Round-ms at which the current sprint window ends. The racer is
   * sprinting iff nowMs < sprintUntilMs. 0 = not sprinting.
   */
  sprintUntilMs: number
  /**
   * Stamina in [0, STAMINA_MAX]. Drains while sprinting, regenerates
   * while walking / idle. New taps don't extend the sprint window when
   * this is 0; mid-sprint, hitting 0 force-clamps `sprintUntilMs` to
   * the current tick's `nowMs` so the racer drops back to walk speed.
   */
  staminaPct: number
  /**
   * Round-ms at which the current boost-pad window ends. Boosted iff
   * nowMs < boostUntilMs. Granted by crossing a boost pad; free of
   * stamina drain and faster than a sprint.
   */
  boostUntilMs: number
  /**
   * Round-ms at which the current jump's airborne window ends. Crossing
   * a hurdle while nowMs < jumpUntilMs clears it cleanly.
   */
  jumpUntilMs: number
  /** Round-ms at which the last jump started — drives the jump cooldown. */
  lastJumpMs: number
  /**
   * Round-ms at which the racer gets back up after a hurdle knockdown.
   * While down the racer is stationary and can't sprint or jump.
   */
  knockdownUntilMs: number
  /** Bitmask of boost-pad indices already consumed (one fire per pad per race). */
  boostPadsHit: number
}

export function makeRacer(id: string): Racer {
  return {
    id,
    positionM: 0,
    velocityMps: 0,
    finished: false,
    finishTimeMs: 0,
    isMoving: false,
    sprintUntilMs: 0,
    staminaPct: STAMINA_INITIAL,
    boostUntilMs: 0,
    jumpUntilMs: 0,
    // Backdated one full cooldown so the first jump tap of a race is
    // honoured even at nowMs = 0.
    lastJumpMs: -HURDLE_JUMP_COOLDOWN_MS,
    knockdownUntilMs: 0,
    boostPadsHit: 0,
  }
}

/** Update the move-key hold state. No-op for finished racers. */
export function setMoving(racer: Racer, isMoving: boolean): void {
  if (racer.finished) return
  racer.isMoving = isMoving
}

/**
 * Register a sprint-key tap. Extends the sprint window by
 * SPRINT_TAP_DURATION_MS but never past SPRINT_MAX_WINDOW_MS above now.
 *
 * No-op when stamina is depleted — a tired racer can't sprint until
 * walking / standing has regenerated some stamina — and while knocked
 * down, so taps banked on the ground can't fire on the get-up frame.
 */
export function triggerSprintTap(racer: Racer, nowMs: number): void {
  if (racer.finished) return
  if (racer.staminaPct <= 0) return
  if (isKnockedDown(racer, nowMs)) return
  const currentEnd = Math.max(nowMs, racer.sprintUntilMs)
  const newEnd = currentEnd + SPRINT_TAP_DURATION_MS
  const hardCap = nowMs + SPRINT_MAX_WINDOW_MS
  racer.sprintUntilMs = Math.min(newEnd, hardCap)
}

/**
 * Advance one physics step. Integrates velocity + position using the
 * caller-supplied dt (ms). Marks `finished` the first step a racer reaches
 * TRACK_LENGTH_M.
 */
export function tick(
  racers: Racer[],
  dtMs: number,
  nowMs: number,
  trackLengthM: number = TRACK_LENGTH_M,
): void {
  const dtSec = dtMs / 1000
  if (dtSec <= 0) return

  for (let i = 0; i < racers.length; i++) {
    const r = racers[i]
    if (r.finished) continue

    const sprinting = nowMs < r.sprintUntilMs
    stepStamina(r, sprinting, nowMs, dtSec)
    // Re-evaluate sprinting after stamina: hitting 0 mid-tick clamps
    // sprintUntilMs to nowMs, so velocity for this step uses walk target.
    const stillSprinting = nowMs < r.sprintUntilMs
    stepVelocity(r, stillSprinting, nowMs, dtSec)
    const prevPositionM = r.positionM
    r.positionM += r.velocityMps * dtSec

    if (r.positionM >= trackLengthM) {
      r.finished = true
      r.finishTimeMs = nowMs
      continue
    }

    // Pads / hurdles crossed in (prevPositionM, positionM] this tick.
    // Effects (boost window, knockdown) land on the next velocity step.
    stepTrackFeatures(r, prevPositionM, nowMs, trackLengthM)
  }
}

/**
 * Drain stamina while sprinting, regen while not. When stamina hits 0
 * mid-sprint, the sprint window is force-clamped to `nowMs` so the
 * velocity step picks up walk-target speed on this same tick.
 */
function stepStamina(racer: Racer, sprinting: boolean, nowMs: number, dtSec: number): void {
  if (sprinting) {
    racer.staminaPct -= SPRINT_DRAIN_PER_S * dtSec
    if (racer.staminaPct <= 0) {
      racer.staminaPct = 0
      racer.sprintUntilMs = nowMs
    }
    return
  }
  const regen = racer.isMoving ? WALK_REGEN_PER_S : IDLE_REGEN_PER_S
  racer.staminaPct = Math.min(STAMINA_MAX, racer.staminaPct + regen * dtSec)
}

/** Is this racer currently inside a sprint burst? */
export function isSprinting(racer: Racer, nowMs: number): boolean {
  return nowMs < racer.sprintUntilMs
}

function stepVelocity(racer: Racer, sprinting: boolean, nowMs: number, dtSec: number): void {
  let target: number
  let accel: number

  if (racer.isMoving) {
    target = movingTargetSpeed(racer, sprinting, nowMs)
    accel = MOVE_ACCEL_MPSS
  } else {
    target = 0
    accel = MOVE_DECEL_MPSS
  }

  const v = racer.velocityMps
  const deltaV = accel * dtSec
  if (v < target) {
    racer.velocityMps = Math.min(target, v + deltaV)
  } else if (v > target) {
    racer.velocityMps = Math.max(target, v - deltaV)
  }

  if (racer.velocityMps > V_MAX_MPS) racer.velocityMps = V_MAX_MPS
}

/**
 * Speed target while the move key is held. Precedence: a knockdown pins
 * the racer to the ground (target 0); otherwise a boost-pad window beats
 * a sprint window beats plain walking.
 */
function movingTargetSpeed(racer: Racer, sprinting: boolean, nowMs: number): number {
  if (isKnockedDown(racer, nowMs)) return 0
  if (isBoosted(racer, nowMs)) return BOOST_TARGET_MPS
  return sprinting ? RUN_TARGET_MPS : WALK_TARGET_MPS
}

/**
 * Rank racers into finish places:
 *   1. Finishers first, ascending finishTimeMs.
 *   2. Same-tick tie: further post-tick positionM wins.
 *   3. Exact float tie: ascending racer id.
 *   4. DNFs after finishers, descending distance. Ties: ascending id.
 */
export function checkFinish(racers: readonly Racer[], timeoutFired: boolean): Placing[] {
  const sorted = racers.slice().sort((a, b) => {
    if (a.finished !== b.finished) return a.finished ? -1 : 1

    if (a.finished && b.finished) {
      if (a.finishTimeMs !== b.finishTimeMs) return a.finishTimeMs - b.finishTimeMs
      if (a.positionM !== b.positionM) return b.positionM - a.positionM
      return a.id.localeCompare(b.id)
    }

    if (a.positionM !== b.positionM) return b.positionM - a.positionM
    return a.id.localeCompare(b.id)
  })

  void timeoutFired
  return sorted.map((r, idx) => ({
    racerId: r.id,
    place: idx + 1,
    finished: r.finished,
    finishTimeMs: r.finished ? r.finishTimeMs : 0,
    distanceM: r.positionM,
  }))
}
