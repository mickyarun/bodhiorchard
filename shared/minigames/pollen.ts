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
 * with a server-seeded RNG and streams their spawn parameters to the client,
 * which renders them deterministically. A pop the client sends is validated
 * server-side — the mote must exist and still be on-screen at the server's
 * clock — so the client can never invent a mote or pop one twice.
 */

/** Game length in seconds. */
export const GAME_SECONDS = 25
/** Seconds between mote spawns. */
export const SPAWN_EVERY_S = 0.55
/** Renderable blossom glyphs; index is server-chosen so both sides agree. */
export const MOTE_EMOJI = ['🌸', '🌼', '💮', '🌺'] as const

/** Below this y (percent, 0 = top) a mote has drifted off the top and dies. */
const DESPAWN_Y = -8
/** Spawn y (percent) — just below the arena floor, so motes rise into view. */
const SPAWN_Y = 104

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

/** Spawn a mote with server-seeded (or test) RNG. `id`/`spawnAtMs` are caller-owned. */
export function spawnMote(id: number, spawnAtMs: number, rng: () => number = Math.random): Mote {
  return {
    id,
    spawnAtMs,
    x: 8 + rng() * 84,
    vy: 9 + rng() * 10,
    vx: (rng() - 0.5) * 6,
    scale: 0.8 + rng() * 0.8,
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
