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
 * Pollen Pop — pure game logic for the timed popping game.
 *
 * Framework-free and shared. The server owns the mote field: it spawns motes
 * with a server-seeded RNG and streams their spawn parameters; the client
 * renders them deterministically. A pop the client sends is validated
 * server-side, so the client can never invent a mote or pop one twice.
 *
 * The round RAMPS: flowers rise faster and spawn on a quicker (jittered)
 * cadence as time runs out, with wide variance in position, drift, size, and
 * speed. On-screen density is hard-capped (MAX_CONCURRENT_MOTES), so the late
 * game is fast and fleeting rather than a flooded click-farm — yet the score
 * keeps climbing (motes cycle), so there's no fixed ceiling.
 */

/** Game length in seconds, and the same in milliseconds. */
export const GAME_SECONDS = 25
export const GAME_MS = GAME_SECONDS * 1000
/** Renderable blossom glyphs; index is server-chosen so both sides agree. */
export const MOTE_EMOJI = ['🌸', '🌼', '💮', '🌺'] as const

/** Spawn interval (ms): starts here and ramps down to the floor below. The
 * floor is deliberately well above zero so the late game speeds up without
 * carpeting the arena in spawns — density is bounded by MAX_CONCURRENT_MOTES. */
export const SPAWN_START_MS = 600
export const SPAWN_MIN_MS = 320
/** Motes rise up to (1 + SPEED_RAMP)× faster by the final second. */
export const SPEED_RAMP = 1.6
/** Hard ceiling on live motes. The screen never crowds past this, so the late
 * game is a reaction test (fast, fleeting targets) rather than a click-farm of
 * a flooded arena. Not a score cap — motes cycle, so pops keep accruing. */
export const MAX_CONCURRENT_MOTES = 8
/** Cadence jitter (±fraction). Spawns land off a fixed metronome so the rhythm
 * can't be memorised; 0.5 RNG is neutral, keeping the cadence deterministic. */
export const SPAWN_JITTER = 0.3

/** Below this y (percent, 0 = top) a mote has drifted off the top and dies. */
const DESPAWN_Y = -8
/** Spawn y (percent) — just below the arena floor, so motes rise into view. */
const SPAWN_Y = 104

/** Normalised round progress (0..1) at `elapsedMs`. */
function progress(elapsedMs: number): number {
  return Math.min(1, Math.max(0, elapsedMs / GAME_MS))
}

/**
 * Time between spawns at a point in the round — eases from SPAWN_START_MS down
 * to SPAWN_MIN_MS so the cadence quickens near the end. The floor stays well
 * above zero; the live count, not the cadence, bounds on-screen density.
 */
export function spawnIntervalMs(elapsedMs: number): number {
  return SPAWN_START_MS - progress(elapsedMs) * (SPAWN_START_MS - SPAWN_MIN_MS)
}

/**
 * The base cadence with ±SPAWN_JITTER randomness applied, so spawns don't fall
 * on a predictable metronome. `rng() === 0.5` is neutral (returns the base),
 * which keeps seeded callers deterministic.
 */
export function jitteredIntervalMs(elapsedMs: number, rng: () => number = Math.random): number {
  return spawnIntervalMs(elapsedMs) * (1 - SPAWN_JITTER + rng() * 2 * SPAWN_JITTER)
}

/**
 * One drifting blossom. Spawn parameters are fixed at creation; position at any
 * later time is a pure function of them, so the server is the source of truth
 * and the client merely interpolates.
 */
export interface Mote {
  id: number
  spawnAtMs: number
  x: number // percent, horizontal start
  vy: number // percent/sec upward
  vx: number // percent/sec horizontal drift
  scale: number
  emojiIndex: number
}

/**
 * Spawn a mote with server-seeded (or test) RNG. `elapsedMs` ramps the rise
 * speed; the spread on position, drift, size, and speed is deliberately wide so
 * trajectories vary shot-to-shot.
 */
export function spawnMote(
  id: number,
  spawnAtMs: number,
  rng: () => number = Math.random,
  elapsedMs = 0,
): Mote {
  const speed = 1 + progress(elapsedMs) * SPEED_RAMP
  return {
    id,
    spawnAtMs,
    x: 6 + rng() * 88,
    vy: (8 + rng() * 14) * speed,
    vx: (rng() - 0.5) * 14,
    scale: 0.7 + rng() * 1.0,
    emojiIndex: Math.floor(rng() * MOTE_EMOJI.length),
  }
}

/** A mote's position (percent) at wall-clock `nowMs`. Pure and deterministic. */
export function motePositionAt(mote: Mote, nowMs: number): { x: number; y: number } {
  const elapsedSec = Math.max(0, (nowMs - mote.spawnAtMs) / 1000)
  return {
    x: mote.x + mote.vx * elapsedSec,
    y: SPAWN_Y - mote.vy * elapsedSec,
  }
}

/** True while the mote is still on-screen (hasn't drifted off the top) at `nowMs`. */
export function isMoteAlive(mote: Mote, nowMs: number): boolean {
  return motePositionAt(mote, nowMs).y > DESPAWN_Y
}
