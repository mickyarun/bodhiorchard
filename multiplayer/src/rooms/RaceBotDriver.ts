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
 * RaceBotDriver — deterministic input synthesis for dev-mode bot racers.
 *
 * Pure functions over the shared physics state: no Colyseus, no
 * Math.random, no physics forks. Bots act exclusively through the same
 * shared entry points human messages use (setMoving, triggerSprintTap,
 * triggerJump), so the simulation can never diverge between a bot lane
 * and a human lane. Called by RaceRoom.simStep immediately before
 * physicsTick each tick.
 *
 * Per-bot variety is derived from the bot's index (parsed from its
 * `bot-<n>` id), never from randomness — the same inputs always produce
 * the same race, which keeps repro of physics/anim bugs trivial.
 */
import { type Racer, setMoving, triggerSprintTap } from "../../../shared/race/RacePhysics"
import { hurdlePositionsM, triggerJump } from "../../../shared/race/RaceTrackFeatures"
import { LOOP_LENGTH_M } from "../../../shared/race/RaceConstants"
import { BOT_USER_ID_PREFIX } from "./RaceRoomHelpers"

/**
 * Sprint-tap cadence per bot: base + index·step. Sustaining a full
 * sprint needs a tap every SPRINT_TAP_DURATION_MS (250 ms), so bot 0
 * (700 ms) sprints in frequent bursts while bot 6 (2140 ms) mostly
 * walks — the field spreads out and finish times differ visibly.
 */
const SPRINT_CADENCE_BASE_MS = 700
const SPRINT_CADENCE_STEP_MS = 240

/**
 * Per-bot jump anticipation: the bot taps jump when it predicts crossing
 * `hurdle − lead` this tick. HURDLE_JUMP_WINDOW_MS is 400 ms, so at
 * typical bot speeds (~3-7 m/s) leads under ~2 m land inside the window
 * (clean clearance) while leads of 4.8-7.5 m expire mid-run-up and the
 * bot clips the hurdle — deliberate, so knockdowns are exercised too.
 */
const JUMP_LEAD_M: readonly number[] = [1.2, 6.5, 0.8, 4.8, 2.0, 7.5, 1.6, 3.6, 0.5]

/**
 * Physical hurdle positions a racer crosses over `raceDistanceM`, in
 * cumulative-arc metres. The bars live once on the loop at fractions of
 * LOOP_LENGTH_M; a multi-lap race crosses each of them once per lap, so
 * lap k contributes loop-position + k·LOOP_LENGTH_M. This is what the bot
 * jump anticipation must line up with, on every lap.
 */
export function hurdleArcPositionsM(raceDistanceM: number): number[] {
  const loopHurdles = hurdlePositionsM(LOOP_LENGTH_M)
  const lapCount = Math.max(1, Math.round(raceDistanceM / LOOP_LENGTH_M))
  const positions: number[] = []
  for (let lap = 0; lap < lapCount; lap++) {
    for (const h of loopHurdles) positions.push(lap * LOOP_LENGTH_M + h)
  }
  return positions
}

/**
 * Drive every bot for one sim tick. `elapsedMs` is the round clock and
 * `dtMs` the tick period — both come from RaceRoom's sim loop so tap
 * scheduling stays aligned with the physics integration. `raceDistanceM`
 * is the finish line (lapCount · LOOP_LENGTH_M); bots aim their jumps at
 * every physical hurdle crossing across all laps.
 */
export function driveBots(
  botRacers: readonly Racer[],
  elapsedMs: number,
  dtMs: number,
  raceDistanceM: number,
): void {
  const hurdles = hurdleArcPositionsM(raceDistanceM)
  const dtSec = dtMs / 1000
  for (const bot of botRacers) {
    if (bot.finished) continue
    // Hold the move key for the whole race — idempotent each tick.
    setMoving(bot, true)

    const index = botIndexFromId(bot.id)

    // Tap exactly once per cadence interval: fire on the tick in which
    // the interval boundary falls. Stamina gating (taps ignored at 0)
    // and knockdown lockout live in triggerSprintTap itself.
    const cadenceMs = SPRINT_CADENCE_BASE_MS + index * SPRINT_CADENCE_STEP_MS
    if (Math.floor(elapsedMs / cadenceMs) > Math.floor((elapsedMs - dtMs) / cadenceMs)) {
      triggerSprintTap(bot, elapsedMs)
    }

    // Jump when this tick is predicted to carry the bot across its
    // per-bot trigger point — a one-shot per hurdle, since position is
    // monotonically non-decreasing. Cooldown/knockdown rules live in
    // triggerJump.
    const leadM = JUMP_LEAD_M[index % JUMP_LEAD_M.length]
    const predictedM = bot.positionM + bot.velocityMps * dtSec
    for (const hurdleM of hurdles) {
      const triggerM = hurdleM - leadM
      if (bot.positionM < triggerM && predictedM >= triggerM) {
        triggerJump(bot, elapsedMs)
      }
    }
  }
}

/** 0-based bot index from a `bot-<n>` id (bots are numbered from 1). */
function botIndexFromId(id: string): number {
  const n = Number.parseInt(id.slice(BOT_USER_ID_PREFIX.length), 10)
  return Number.isFinite(n) && n >= 1 ? n - 1 : 0
}
